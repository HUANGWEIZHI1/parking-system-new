from flask_cors import CORS
from flask import Flask, request, session, jsonify
from functools import wraps
import pymysql
import os
from flask_apscheduler import APScheduler
from datetime import datetime

app = Flask(__name__)
CORS(app, supports_credentials=True)
app.secret_key = "my_secret_2026_parking"  # session加密密钥

# MySQL数据库连接函数
def get_db_conn():
    conn = pymysql.connect(
        host='127.0.0.1',
        user='root',
        password='123456',  # =========【务必改成你本机MySQL的root密码！】=========
        database='parking_db',
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )
    return conn

# 登录校验装饰器
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return jsonify({"code":401,"msg":"Please log in first"}),401
        return f(*args, **kwargs)
    return decorated_function

# ---------------- 定时任务初始化 ----------------
scheduler = APScheduler()
def auto_update_parking_status():
    """定时任务：扫描预约，到达时间自动把车位从预留(2)改为占用(1)"""
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[定时任务运行] 当前时间 {now_str}")
    conn = get_db_conn()
    cur = conn.cursor()
    # 查询所有处于预约状态的记录
    cur.execute('''
        SELECT r.id, r.space_id, r.start_time, s.status
        FROM reservations r
        LEFT JOIN spaces s ON r.space_id = s.id
        WHERE s.status = 2
    ''')
    all_reservations = cur.fetchall()
    for res in all_reservations:
        # 增加判断：如果start_time为空，直接跳过
        if res["start_time"] is None:
            continue
        try:
            # MySQL读出datetime对象，不再需要字符串replace解析！
            reserve_time = res["start_time"]
            if reserve_time <= now:
                cur.execute("UPDATE spaces SET status=%s WHERE id=%s", (1, res["space_id"],))
                print(f"✅车位ID:{res['space_id']} 预约时间到期，状态更新为占用")
        except Exception as e:
            print(f"解析时间出错：{e}")
    conn.commit()
    conn.close()


# 每30秒跑一次
scheduler.add_job("parking_job", auto_update_parking_status, trigger="interval", seconds=30)
scheduler.init_app(app)
scheduler.start()
# ------------------------------------------------

# ===================== 登录相关接口 =====================
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")
    conn = get_db_conn()
    cur = conn.cursor()
    # 根据用户名查询用户
    cur.execute("SELECT * FROM user WHERE username = %s", (username,))
    user = cur.fetchone()
    conn.close()
    # 校验用户名和明文密码
    if user and user["password"] == password:
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["role"] = user["role"]
        return {"code":200,"msg":"success","role":user["role"]}
    else:
        return {"code":400,"msg":"Username or password error"}

# 获取当前登录用户信息
@app.route('/api/get-current-user', methods=['GET'])
@login_required
def get_current_user():
    return jsonify({"code":200,"username":session["username"],"user_id":session["user_id"],"role":session["role"]})

# 退出登录接口
@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"code":200,"msg":"Logout success"})

# 管理员：查询系统全部预约记录
@app.route('/api/all-reservations', methods=['GET'])
@login_required
def get_all_reservations():
    conn = get_db_conn()
    cur = conn.cursor()
    sql = '''
    SELECT r.*, s.location, u.username
    FROM reservations r
    LEFT JOIN spaces s ON r.space_id = s.id
    LEFT JOIN user u ON r.user_id = u.id
    '''
    cur.execute(sql)
    rows = cur.fetchall()
    data = [dict(row) for row in rows]
    conn.close()
    return jsonify({"code":200,"data":data})

# ===================== 车位接口 =====================
# 获取全部车位
@app.route('/api/spaces', methods=['GET'])
@login_required
def get_spaces():
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM spaces")
    rows = cur.fetchall()
    data = [dict(row) for row in rows]
    conn.close()
    return jsonify({"code":200,"data":data})

# 管理员更新车位状态
@app.route('/api/space/update', methods=['POST'])
@login_required
def update_space():
    data = request.get_json()
    space_id = data.get("space_id")
    status = data.get("status")
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("UPDATE spaces SET status=%s WHERE id=%s", (status, space_id))
    conn.commit()
    conn.close()
    return jsonify({"code":200,"msg":"Updated successfully"})

# ===================== 预约相关接口 =====================
# 提交预约
@app.route('/api/reserve', methods=['POST'])
@login_required
def reserve_space():
    data = request.get_json()
    user_id = data.get("user_id")
    space_id = data.get("space_id")
    start_time = data.get("start_time")
    conn = get_db_conn()
    cur = conn.cursor()
    # ============【校验该用户是否已有生效预约（已预约/占用都拦截）】============
    cur.execute('''
        SELECT r.* FROM reservations r
        LEFT JOIN spaces s ON r.space_id = s.id
        WHERE r.user_id = %s AND s.status IN (1,2)
    ''', (user_id,))
    exist = cur.fetchone()
    if exist:
        conn.close()
        return jsonify({"code":400,"msg":"You already have an active reservation. Cannot reserve another parking space."}),400
    # =================================================================
    # 判断车位是否空闲
    cur.execute("SELECT * FROM spaces WHERE id=%s",(space_id,))
    space = cur.fetchone()
    if space is None or space["status"] !=0:
        conn.close()
        return jsonify({"code":400,"msg":"Parking space is unavailable"})
    # 新增预约记录，修改车位状态为已预约2
    cur.execute("INSERT INTO reservations(space_id,user_id,start_time) VALUES (%s,%s,%s)",(space_id,user_id,start_time))
    cur.execute("UPDATE spaces SET status=%s, start_time=%s WHERE id=%s",(2, start_time, space_id))
    conn.commit()
    conn.close()
    return jsonify({"code":200,"msg":"Reservation submitted successfully"})

# 取消预约
@app.route('/api/cancel-reserve', methods=['POST'])
@login_required
def cancel_reserve():
    data = request.get_json()
    user_id = data.get("user_id")
    space_id = data.get("space_id")
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM reservations WHERE space_id=%s AND user_id=%s",(space_id,user_id))
    cur.execute("UPDATE spaces SET status=%s, start_time=null WHERE id=%s",(0, space_id,))
    conn.commit()
    conn.close()
    return jsonify({"code":200,"msg":"Reservation cancelled successfully"})

# 查询用户预约记录
@app.route('/api/reservations', methods=['GET'])
@login_required
def get_reservations():
    user_id = request.args.get("user_id")
    conn = get_db_conn()
    cur = conn.cursor()
    sql = '''
    SELECT r.*, s.location
    FROM reservations r
    LEFT JOIN spaces s ON r.space_id = s.id
    WHERE r.user_id = %s
    '''
    cur.execute(sql,(user_id,))
    rows = cur.fetchall()
    data = [dict(row) for row in rows]
    conn.close()
    return jsonify({"code":200,"data":data})


def init_mysql_db():
    # 本地MySQL连接信息
    conn = pymysql.connect(
        host="127.0.0.1",
        port=3306,
        user="root",
        password="123456", # =========【务必改成你本机MySQL的root密码！】=========
        charset="utf8mb4"
    )
    cursor = conn.cursor()
    # 建库+建表+插入数据SQL
    sql_script = """
CREATE DATABASE IF NOT EXISTS parking_db DEFAULT CHARACTER SET utf8mb4;
USE parking_db;
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS user;
CREATE TABLE user(
    id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(50) NOT NULL UNIQUE,
    password VARCHAR(50) NOT NULL,
    role VARCHAR(20) NOT NULL
);
DROP TABLE IF EXISTS spaces;
CREATE TABLE spaces(
    id INT PRIMARY KEY AUTO_INCREMENT,
    location VARCHAR(50) NOT NULL,
    status TINYINT NOT NULL,
    start_time DATETIME NULL
);
DROP TABLE IF EXISTS reservations;
CREATE TABLE reservations(
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    space_id INT NOT NULL,
    start_time DATETIME,
    FOREIGN KEY(user_id) REFERENCES user(id),
    FOREIGN KEY(space_id) REFERENCES spaces(id)
);
INSERT INTO user(username,password,role) VALUES
('admin','admin123','admin'),
('testuser','test123','user');
INSERT INTO spaces(location,status) VALUES
('A01',0),('A02',0),('A03',0),('B01',0),('B02',0);
SET FOREIGN_KEY_CHECKS = 1;
"""
    # 按分号分割多条SQL执行
    for sql in sql_script.split(";"):
        sql = sql.strip()
        if sql:
            cursor.execute(sql)
    conn.commit()
    cursor.close()
    conn.close()
    print("✅ MySQL数据库、数据表、初始测试数据全部创建成功！")



if __name__ == '__main__':
    # =========【第一次运行，打开下面这行；数据库建好后，必须注释掉！】=========
    #init_mysql_db()
    #init_db()
    app.run(debug=True)

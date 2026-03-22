import psycopg2

# connect to PostgreSQL
conn = psycopg2.connect(
    host="localhost",
    database="cdn_analyzer",
    user="postgres",
    password="180825"   # use your password
)

cur = conn.cursor()

# function to save data
def save_log(data):

    query = """
    INSERT INTO logs(url, response_time, status_code)
    VALUES(%s, %s, %s)
    """

    cur.execute(query, (
        data["url"],
        data["response_time"],
        data["status"]
    ))

    conn.commit()
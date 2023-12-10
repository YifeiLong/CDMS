import logging
import psycopg2


class Store:
    # database: str

    def __init__(self):
        self.db = psycopg2.connect(
            dbname="be",
            user="postgres",
            password="longyifei1206",
            host="localhost",
            port="5432"
        )
        self.init_tables()

    def init_tables(self):
        try:
            conn = self.get_db_conn()
            cur = conn.cursor()

            cur.execute(
                "CREATE TABLE IF NOT EXISTS \"user\" ("
                "user_id TEXT PRIMARY KEY, password TEXT NOT NULL, "
                "balance INTEGER NOT NULL, token TEXT, terminal TEXT);"
            )

            cur.execute(
                "CREATE TABLE IF NOT EXISTS \"user_store\"("
                "user_id TEXT, store_id TEXT, PRIMARY KEY(user_id, store_id));"
            )

            cur.execute(
                "CREATE TABLE IF NOT EXISTS \"store\"( "
                "store_id TEXT, book_id TEXT, book_info TEXT, stock_level INTEGER,"
                " PRIMARY KEY(store_id, book_id))"
            )

            cur.execute(
                "CREATE TABLE IF NOT EXISTS \"new_order\"( "
                "order_id TEXT PRIMARY KEY, user_id TEXT, store_id TEXT)"
            )

            cur.execute(
                "CREATE TABLE IF NOT EXISTS \"new_order_detail\"( "
                "order_id TEXT, book_id TEXT, count INTEGER, price INTEGER,  "
                "PRIMARY KEY(order_id, book_id))"
            )

            conn.commit()
            cur.close()
        except psycopg2.Error as e:
            logging.error(e)

    def get_db_conn(self):
        return self.db


database_instance: Store = None


def init_database():
    global database_instance
    database_instance = Store()


def get_db_conn():
    global database_instance
    return database_instance.get_db_conn()

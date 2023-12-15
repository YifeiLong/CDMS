import logging
import psycopg2
import pymongo


class Store:
    database: str

    def __init__(self):
        self.database = "be"

        self.db = psycopg2.connect(
            dbname=self.database,
            user="postgres",
            password="longyifei1206",
            host="localhost",
            port="5432"
        )
        # MongoDB存放大段文本和blob数据，book_detail
        self.client = pymongo.MongoClient("mongodb://localhost:27017/")
        self.text_db = self.client.get_database(self.database)
        self.book_detail_col = None

        self.init_tables()

    def init_tables(self):
        try:
            cur = self.db.cursor()

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

            cur.execute(
                "CREATE TABLE IF NOT EXISTS \"history_order\" ("
                "order_id TEXT, store_id TEXT, user_id TEXT, book_id TEXT, "
                "book_count INTEGER, price INTEGER, "
                "is_cancelled BOOLEAN, is_paid BOOLEAN, is_delivered BOOLEAN, is_received BOOLEAN, "
                "PRIMARY KEY(order_id, book_id))"
            )

            self.db.commit()
            cur.close()

            self.book_detail_col = self.text_db.create_collection("book_detail")
            self.book_detail_col.create_index([("tags", pymongo.ASCENDING)])
            self.book_detail_col.create_index([("book_id", pymongo.ASCENDING)], unique=True)
            self.book_detail_col.create_index([("author", pymongo.ASCENDING)])
            self.book_detail_col.create_index([("description", "text")])  # 所有文本信息

        except psycopg2.Error as e:
            logging.error(e)

    def get_db_conn(self):
        return self.db, self.text_db


database_instance: Store = None


def init_database():
    global database_instance
    database_instance = Store()


def get_db_conn():
    global database_instance
    return database_instance.get_db_conn()

import psycopg2
import re
import jieba
import json
import pymongo
from be.model import error
from be.model import db_conn


class Seller(db_conn.DBConn):
    def __init__(self):
        super().__init__()

    # 分词
    def split_words(self, text):
        words = re.sub(r'[^\w\s\n]', '', text)
        words = re.sub(r'\n', '', words)
        res = jieba.cut(words, cut_all=False)
        res_str = ' '.join(res)
        return res_str

    def add_book(
        self,
        user_id: str,
        store_id: str,
        book_id: str,
        book_json_str: str,
        stock_level: int,
    ):
        try:
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id)
            if not self.store_id_exist(store_id):
                return error.error_non_exist_store_id(store_id)
            if self.book_id_exist(store_id, book_id):
                return error.error_exist_book_id(book_id)

            self.cursor.execute(
                "INSERT into \"store\"(store_id, book_id, book_info, stock_level)"
                "VALUES (%s, %s, %s, %s)",
                (store_id, book_id, book_json_str, stock_level),
            )

            # 加入全站书籍名录
            book_detail_col = self.textdb.get_collection("book_detail")
            row = book_detail_col.find_one({'book_id': book_id})
            if row is None:
                book_info = json.loads(book_json_str)
                des_str = book_info["title"] + " " + self.split_words(book_info["title"]) + " " + \
                          self.split_words(book_info["book_intro"]) + " " + self.split_words(book_info["content"])
                book_data = {
                    "book_id": book_info["id"],
                    "title": book_info["title"],
                    "author": book_info["author"],
                    "book_intro": book_info["book_intro"],
                    "content": book_info["content"],
                    "tags": book_info["tags"],
                    "description": des_str
                }
                book_detail_col.insert_one(book_data)

            self.conn.commit()
        except Exception as e:
            return 530, "{}".format(str(e))
        return 200, "ok"

    def add_stock_level(
        self, user_id: str, store_id: str, book_id: str, add_stock_level: int
    ):
        try:
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id)
            if not self.store_id_exist(store_id):
                return error.error_non_exist_store_id(store_id)
            if not self.book_id_exist(store_id, book_id):
                return error.error_non_exist_book_id(book_id)

            self.cursor.execute(
                "UPDATE \"store\" SET stock_level = stock_level + %s "
                "WHERE store_id = %s AND book_id = %s",
                (add_stock_level, store_id, book_id),
            )
            self.conn.commit()

        except Exception as e:
            return 530, "{}".format(str(e))
        return 200, "ok"

    def create_store(self, user_id: str, store_id: str) -> (int, str):
        try:
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id)
            if self.store_id_exist(store_id):
                return error.error_exist_store_id(store_id)
            self.cursor.execute(
                "INSERT into \"user_store\"(store_id, user_id)" "VALUES (%s, %s)",
                (store_id, user_id),
            )
            self.conn.commit()

        except Exception as e:
            return 530, "{}".format(str(e))
        return 200, "ok"

    # 发货
    def deliver_book(self, user_id: str, store_id: str, order_id: str):
        try:
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id)
            if not self.store_id_exist(store_id):
                return error.error_non_exist_store_id(store_id)

            self.cursor.execute(
                "SELECT is_cancelled, is_paid FROM \"history_order\" WHERE order_id = %s;",
                (order_id,),
            )
            if self.cursor.rowcount == 0:
                return error.error_invalid_order_id(order_id)

            orders = self.cursor.fetchall()
            for order in orders:
                if order[0] is True:
                    return error.error_order_cancelled(order_id)
                if order[1] is False:
                    return error.error_order_not_paid(order_id)

            # 更新历史订单状态为已发货
            self.cursor.execute(
                "UPDATE \"history_order\" SET is_delivered = %s WHERE order_id = %s;",
                (True, order_id),
            )
            self.conn.commit()
            return 200, "book deliver ok"

        except Exception as e:
            return 530, f"{str(e)}"

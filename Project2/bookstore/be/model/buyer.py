import uuid
import json
import logging
import psycopg2
import pymongo
import re
import jieba
from datetime import datetime
from be.model import db_conn
from be.model import error


class Buyer(db_conn.DBConn):
    def __init__(self):
        super().__init__()

    def new_order(
        self, user_id: str, store_id: str, id_and_count: [(str, int)]
    ):
        order_id = ""
        try:
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id) + (order_id,)
            if not self.store_id_exist(store_id):
                return error.error_non_exist_store_id(store_id) + (order_id,)
            uid = "{}_{}_{}".format(user_id, store_id, str(uuid.uuid1()))

            for book_id, count in id_and_count:
                self.cursor.execute(
                    "SELECT book_id, stock_level, book_info FROM \"store\" "
                    "WHERE store_id =%s AND book_id =%s;",
                    (store_id, book_id),
                )
                row = self.cursor.fetchone()
                if row is None:
                    return error.error_non_exist_book_id(book_id) + (order_id,)

                stock_level = row[1]
                book_info = row[2]
                book_info_json = json.loads(book_info)
                price = book_info_json.get("price")

                if stock_level < count:
                    return error.error_stock_level_low(book_id) + (order_id,)

                self.cursor.execute(
                    "UPDATE \"store\" set stock_level = stock_level - %s "
                    "WHERE store_id = %s and book_id = %s and stock_level >= %s; ",
                    (count, store_id, book_id, count),
                )
                if self.cursor.rowcount == 0:
                    return error.error_stock_level_low(book_id) + (order_id,)

                self.cursor.execute(
                    "INSERT INTO \"new_order_detail\"(order_id, book_id, count, price) "
                    "VALUES(%s, %s, %s, %s);",
                    (uid, book_id, count, price),
                )

                # 将信息存入历史订单，每本书一行
                self.cursor.execute(
                    "INSERT INTO \"history_order\" (order_id, store_id, user_id, book_id, book_count, price, is_cancelled, is_paid, is_delivered, is_received) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);",
                    (uid, store_id, user_id, book_id, count, price, False, False, False, False),
                )

            self.cursor.execute(
                "INSERT INTO \"new_order\"(order_id, store_id, user_id) "
                "VALUES(%s, %s, %s);",
                (uid, store_id, user_id),
            )

            self.conn.commit()
            order_id = uid

        except Exception as e:
            logging.info("530, {}".format(str(e)))
            return 530, "{}".format(str(e)), ""

        return 200, "ok", order_id

    def payment(self, user_id: str, password: str, order_id: str):
        try:
            self.cursor.execute(
                "SELECT order_id, user_id, store_id FROM \"new_order\" WHERE order_id = %s",
                (order_id,),
            )
            row = self.cursor.fetchone()
            if row is None:
                return error.error_invalid_order_id(order_id)

            order_id = row[0]
            buyer_id = row[1]
            store_id = row[2]

            if buyer_id != user_id:
                return error.error_authorization_fail()

            self.cursor.execute(
                "SELECT balance, password FROM \"user\" WHERE user_id = %s;", (buyer_id,)
            )
            row = self.cursor.fetchone()
            if row is None:
                return error.error_non_exist_user_id(buyer_id)
            balance = row[0]

            if password != row[1]:
                return error.error_authorization_fail()

            self.cursor.execute(
                "SELECT store_id, user_id FROM \"user_store\" WHERE store_id = %s;",
                (store_id,),
            )
            row = self.cursor.fetchone()
            if row is None:
                return error.error_non_exist_store_id(store_id)

            seller_id = row[1]

            if not self.user_id_exist(seller_id):
                return error.error_non_exist_user_id(seller_id)

            self.cursor.execute(
                "SELECT book_id, count, price FROM \"new_order_detail\" WHERE order_id = %s;",
                (order_id,),
            )
            total_price = 0
            for row in self.cursor.fetchall():
                count = row[1]
                price = row[2]
                total_price = total_price + price * count

            if balance < total_price:
                return error.error_not_sufficient_funds(order_id)

            self.cursor.execute(
                "UPDATE \"user\" set balance = balance - %s WHERE user_id = %s AND balance >= %s",
                (total_price, buyer_id, total_price),
            )
            if self.cursor.rowcount == 0:
                return error.error_not_sufficient_funds(order_id)

            self.cursor.execute(
                "UPDATE \"user\" set balance = balance + %s WHERE user_id = %s",
                (total_price, buyer_id),
            )

            if self.cursor.rowcount == 0:
                return error.error_non_exist_user_id(buyer_id)

            self.cursor.execute(
                "DELETE FROM \"new_order\" WHERE order_id = %s", (order_id,)
            )
            if self.cursor.rowcount == 0:
                return error.error_invalid_order_id(order_id)

            # 更新历史订单状态为已支付
            self.cursor.execute(
                "SELECT * FROM \"history_order\" WHERE order_id = %s;",
                (order_id,),
            )
            if self.cursor.rowcount == 0:
                return error.error_invalid_order_id(order_id)

            self.cursor.execute(
                "UPDATE \"history_order\" SET is_paid = %s WHERE order_id = %s AND user_id = %s;",
                (True, order_id, user_id),
            )

            self.cursor.execute(
                "DELETE FROM \"new_order_detail\" WHERE order_id = %s", (order_id,)
            )
            if self.cursor.rowcount == 0:
                return error.error_invalid_order_id(order_id)

            self.conn.commit()

        except Exception as e:
            return 530, "{}".format(str(e))

        return 200, "ok"

    def add_funds(self, user_id, password, add_value):
        try:
            self.cursor.execute(
                "SELECT password FROM \"user\" WHERE user_id=%s", (user_id,)
            )
            row = self.cursor.fetchone()
            if row is None:
                return error.error_authorization_fail()

            if row[0] != password:
                return error.error_authorization_fail()

            self.cursor.execute(
                "UPDATE \"user\" SET balance = balance + %s WHERE user_id = %s",
                (add_value, user_id),
            )
            if self.cursor.rowcount == 0:
                return error.error_non_exist_user_id(user_id)

            self.conn.commit()

        except Exception as e:
            return 530, "{}".format(str(e))

        return 200, "ok"

    # 收货
    def receive_book(self, user_id: str, order_id: str):
        try:
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id)

            self.cursor.execute(
                "SELECT is_cancelled, is_delivered FROM \"history_order\" WHERE order_id = %s;",
                (order_id,),
            )
            if self.cursor.rowcount == 0:
                return error.error_invalid_order_id(order_id)

            order = self.cursor.fetchone()
            is_cancelled = order[0]
            if is_cancelled is True:
                return error.error_order_cancelled(order_id)
            is_delivered = order[1]
            if is_delivered is False:
                return error.error_order_not_delivered(order_id)

            # 更新历史订单状态为已收货
            self.cursor.execute(
                "UPDATE \"history_order\" SET is_received = %s WHERE order_id = %s;",
                (True, order_id),
            )
            self.conn.commit()

        except Exception as e:
            return 530, "{}".format(str(e))

        return 200, "ok"

    # 买家主动取消订单
    def buyer_cancel_order(self, user_id: str, order_id: str):
        try:
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id)

            self.cursor.execute(
                "SELECT order_id, is_cancelled, is_paid, store_id, book_id, book_count FROM \"history_order\" WHERE order_id = %s;",
                (order_id,),
            )
            if self.cursor.rowcount == 0:
                return error.error_invalid_order_id(order_id)

            orders = self.cursor.fetchall()
            for order in orders:
                is_cancelled = order[1]
                if is_cancelled is True:
                    return error.error_order_cancelled(order_id)
                # 订单状态为已支付时无法取消订单
                is_paid = order[2]
                if is_paid is True:
                    return error.error_order_cancellation_fail(order_id)
                self.cancel_order(order, order_id)

            self.conn.commit()

        except Exception as e:
            return 530, "{}".format(str(e))

        return 200, "ok, order cancelled"

    # 超时自动取消订单
    def overtime_cancel_order(self):
        try:
            living_time = 15 * 60  # 未支付订单保留15分钟
            self.cursor.execute(
                "SELECT order_id, is_cancelled, is_paid, store_id, book_id, book_count FROM \"history_order\";"
            )
            # 还没有产生订单
            if self.cursor.rowcount == 0:
                return 200, "ok"

            num_cancelled = 0
            orders = self.cursor.fetchall()

            for order in orders:
                order_id = order[0]
                is_cancelled = order[1]
                is_paid = order[2]
                if is_cancelled is True or is_paid is True:
                    continue

                # 获取 UUID 时间戳
                parts = order_id.split("_")
                l = len(parts)
                uid = uuid.UUID(parts[l - 1])

                # 转换 UUID 时间戳为可读的时间格式
                timestamp = (uid.time - 0x01b21dd213814000) / 1e7
                datetime_obj = datetime.utcfromtimestamp(timestamp)

                # 计算时间差
                current_time = datetime.now()
                time_passed = (current_time - datetime_obj).total_seconds()
                if time_passed > living_time:
                    self.cancel_order(order, order_id)
                    num_cancelled += 1

            self.conn.commit()

        except Exception as e:
            return 530, "{}".format(str(e))

        return 200, "ok, {} orders cancelled".format(num_cancelled)

    # 取消订单
    def cancel_order(self, order, order_id):
        self.cursor.execute(
            "UPDATE \"history_order\" SET is_cancelled = %s WHERE order_id = %s;",
            (True, order_id),
        )

        # 还原书籍库存
        self.cursor.execute(
            "UPDATE \"store\" SET stock_level = stock_level + %s WHERE store_id = %s AND book_id = %s;",
            (order[5], order[3], order[4]),
        )

        # 删除new_order和new_order_detail中的相关文档
        self.cursor.execute(
            "DELETE FROM \"new_order\" WHERE order_id = %s;",
            (order_id,),
        )
        if self.cursor.rowcount == 0:
            return error.error_invalid_order_id(order_id)

        self.cursor.execute(
            "DELETE FROM \"new_order_detail\" WHERE order_id = %s;",
            (order_id,),
        )
        if self.cursor.rowcount == 0:
            return error.error_invalid_order_id(order_id)

        self.conn.commit()

    # 搜索历史订单
    def search_history_order(self, user_id, order_id, page, per_page):
        try:
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id)

            if order_id == "":
                self.cursor.execute(
                    "SELECT * FROM \"history_order\" WHERE user_id = %s;",
                    (user_id,),
                )
                if self.cursor.rowcount == 0:
                    return error.error_non_history_order(user_id)
                order = self.cursor.fetchall()
                res = order

                if self.cursor.rowcount > per_page:
                    start = (page - 1) * per_page
                    end = start + per_page
                    if end > self.cursor.rowcount:
                        res = order[-per_page:]
                    else:
                        res = order[start:end]

            else:
                self.cursor.execute(
                    "SELECT * FROM \"history_order\" WHERE order_id = %s AND user_id = %s;",
                    (order_id, user_id),
                )
                if self.cursor.rowcount == 0:
                    return error.error_non_history_order(user_id)
                order = self.cursor.fetchall()
                res = order

                if self.cursor.rowcount > per_page:
                    start = (page - 1) * per_page
                    end = start + per_page
                    if end > self.cursor.rowcount:
                        res = order[-per_page:]
                    else:
                        res = order[start:end]

            self.conn.commit()
            return 200, f"{str(res)}"

        except Exception as e:
            return 530, "{}".format(str(e))

    # 搜书
    def search_book(self, store_id, title, author, intro, content, tags, page, per_page):
        try:
            book_detail_col = self.textdb.get_collection("book_detail")
            find_condition = {}

            # 当前店铺搜索
            if store_id:
                self.cursor.execute(
                    "SELECT book_id FROM \"store\" WHERE store_id = %s;", (store_id,)
                )
                if self.cursor.rowcount == 0:
                    return error.error_non_exist_store_id(store_id)

                book_id_store = []
                book_ids = self.cursor.fetchall()
                for id in book_ids:
                    book_id_store.append(id[0])

                find_condition["book_id"] = {"$in": book_id_store}

                # 根据作者和标签信息进行第二步筛选
                if author != "":
                    find_condition["author"] = author
                if tags:
                    find_condition["tags"] = {"$in": tags}
                book1 = book_detail_col.find(find_condition, {"_id": 0, "description": 0})
                book_id = []
                for book in book1:
                    book_id.append(book["book_id"])

                # 根据文本信息（标题、内容、目录）进行第三步筛选
                search_des = ""
                if title is not None and title != "":
                    search_des += title
                if content is not None and content != "":
                    search_des += content
                if intro is not None and intro != "":
                    search_des += intro

                if search_des != "":
                    des_words = self.split_words(search_des)
                    res_id = []
                    for word in des_words:
                        books = book_detail_col.find({"book_id": {"$in": book_id}, "$text": {"$search": word}},
                                                     {"_id": 0, "book_id": 1})
                        if books is not None:
                            for book in books:
                                res_id.append(book["book_id"])

                    res_id = list(set(res_id))
                    if len(res_id) != 0:
                        book_info = book_detail_col.find({"book_id": {"$in": res_id}}, {"_id": 0, "description": 0})
                    else:
                        return error.error_non_search_result()

                    num_col = sum(1 for _ in book_info)
                    if num_col == 0:
                        return error.error_non_search_result()

                    res = self.paging(book_info, page, per_page, num_col)
                else:
                    book1.rewind()
                    num_col = sum(1 for _ in book1)
                    if num_col == 0:
                        return error.error_non_search_result()

                    res = self.paging(book1, page, per_page, num_col)

                self.conn.commit()
                return 200, f"{str(res)}"

            # 全站搜索
            else:
                # 根据作者和标签信息进行第一步筛选
                if author != "":
                    find_condition["author"] = author
                if tags:
                    find_condition["tags"] = {"$in": tags}
                book1 = book_detail_col.find(find_condition, {"_id": 0})
                book_id = []
                for book in book1:
                    book_id.append(book["book_id"])

                # 根据文本信息（标题、内容、目录）进行第二步筛选
                search_des = ""
                if title is not None and title != "":
                    search_des += title
                if content is not None and content != "":
                    search_des += content
                if intro is not None and intro != "":
                    search_des += intro

                if search_des != "":
                    des_words = self.split_words(search_des)
                    res_id = []
                    for word in des_words:
                        books = book_detail_col.find({"book_id": {"$in": book_id}, "$text": {"$search": word}},
                                                     {"_id": 0, "book_id": 1})
                        if books is not None:
                            for book in books:
                                res_id.append(book["book_id"])

                    res_id = list(set(res_id))
                    if len(res_id) != 0:
                        book_info = book_detail_col.find({"book_id": {"$in": res_id}}, {"_id": 0, "description": 0})
                    else:
                        return error.error_non_search_result()

                    num_col = sum(1 for _ in book_info)
                    if num_col == 0:
                        return error.error_non_search_result()

                    res = self.paging(book_info, page, per_page, num_col)

                else:
                    book1.rewind()
                    num_col = sum(1 for _ in book1)
                    if num_col == 0:
                        return error.error_non_search_result()

                    res = self.paging(book1, page, per_page, num_col)

                return 200, f"{str(res)}"

        except Exception as e:
            return 530, "{}".format(str(e))

    # 分词
    def split_words(self, text):
        words = re.sub(r'[^\w\s\n]', '', text)
        words = re.sub(r'\n', '', words)
        res = jieba.cut(words, cut_all=False)
        res_list = []
        for word in res:
            res_list.append(word)
        res_list = list(set(res_list))
        return res_list

    # 分页
    def paging(self, cursor, page, per_page, num_col):
        cursor.rewind()
        res = list(cursor)
        if num_col > per_page:
            start = (page - 1) * per_page
            end = start + per_page
            if end > num_col:
                res = res[-per_page:]
            else:
                res = res[start:end]
        return res

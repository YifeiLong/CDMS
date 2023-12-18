import uuid
import json
import logging
import re
import jieba
from datetime import datetime
from sqlalchemy import and_

from be.model import db_conn
from be.model import error
from be.model import store


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
                row = self.session.query(store.StoreTable).filter_by(store_id=store_id, book_id=book_id).first()
                if row is None:
                    return error.error_non_exist_book_id(book_id) + (order_id,)

                stock_level = row.stock_level
                book_info = row.book_info
                book_info_json = json.loads(book_info)
                price = book_info_json.get("price")

                if stock_level < count:
                    return error.error_stock_level_low(book_id) + (order_id,)

                row = self.session.query(store.StoreTable).filter(
                    and_(store.StoreTable.store_id == store_id, store.StoreTable.book_id == book_id,
                         store.StoreTable.stock_level >= count)
                ).first()
                if row:
                    row.stock_level -= count
                    self.session.add(row)
                else:
                    return error.error_stock_level_low(book_id) + (order_id,)

                new_order_detail = store.NewOrderDetail(order_id=uid, book_id=book_id, count=count, price=price)
                self.session.add(new_order_detail)

                # 将信息存入历史订单，每本书一行
                history_order = store.HistoryOrder(
                    order_id=uid,
                    store_id=store_id,
                    user_id=user_id,
                    book_id=book_id,
                    book_count=count,
                    price=price,
                    is_cancelled=False,
                    is_paid=False,
                    is_delivered=False,
                    is_received=False
                )
                self.session.add(history_order)

            new_order = store.NewOrder(order_id=order_id, store_id=store_id, user_id=user_id)
            self.session.add(new_order)

            self.session.commit()
            order_id = uid

        except Exception as e:
            logging.info("530, {}".format(str(e)))
            return 530, "{}".format(str(e)), ""

        return 200, "ok", order_id

    def payment(self, user_id: str, password: str, order_id: str):
        try:
            row = self.session.query(store.NewOrder).filter_by(order_id=order_id).first()
            if row is None:
                return error.error_invalid_order_id(order_id)

            order_id = row.order_id
            buyer_id = row.buyer_id
            store_id = row.store_id

            if buyer_id != user_id:
                return error.error_authorization_fail()

            row = self.session.query(store.User).filter_by(user_id=buyer_id).first()
            if row is None:
                return error.error_non_exist_user_id(buyer_id)
            balance = row.balance

            if password != row.password:
                return error.error_authorization_fail()

            row = self.session.query(store.UserStore).filter_by(store_id=store_id).first()
            if row is None:
                return error.error_non_exist_store_id(store_id)

            seller_id = row.user_id

            if not self.user_id_exist(seller_id):
                return error.error_non_exist_user_id(seller_id)

            rows = self.session.query(store.NewOrderDetail).filter_by(order_id=order_id).all()
            total_price = 0
            for row in rows:
                count = row.count
                price = row.price
                total_price = total_price + price * count

            if balance < total_price:
                return error.error_not_sufficient_funds(order_id)

            rowcount = self.session.query(store.User).filter(store.User.user_id == buyer_id,
                                                        store.User.balance >= total_price).update(
                {store.User.balance: (store.User.balance - total_price)})
            if rowcount == 0:
                return error.error_not_sufficient_funds(order_id)

            rowcount = self.session.query(store.User).filter_by(user_id=seller_id).update(
                {'balance': store.User.balance + total_price})
            if rowcount == 0:
                return error.error_non_exist_user_id(seller_id)

            rowcount = self.session.query(store.NewOrder).filter_by(order_id=order_id).delete()
            if rowcount == 0:
                return error.error_invalid_order_id(order_id)

            # 更新历史订单状态为已支付
            rowcount = self.session.query(store.HistoryOrder).filter_by(order_id=order_id, user_id=buyer_id).update(
                {'is_paid': True}
            )
            if rowcount == 0:
                return error.error_invalid_order_id(order_id)

            rowcount = self.session.query(store.NewOrderDetail).filter_by(order_id=order_id).delete()
            if rowcount == 0:
                return error.error_invalid_order_id(order_id)

            self.session.commit()

        except Exception as e:
            return 530, "{}".format(str(e))

        return 200, "ok"

    def add_funds(self, user_id, password, add_value):
        try:
            row = self.session.query(store.User).filter_by(user_id=user_id).first()
            if row is None:
                return error.error_authorization_fail()

            if row.password != password:
                return error.error_authorization_fail()

            rowcount = self.session.query(store.User).filter_by(user_id=user_id).update(
                {'balance': store.User.balance + add_value})
            if rowcount == 0:
                return error.error_non_exist_user_id(user_id)

            self.session.commit()

        except Exception as e:
            return 530, "{}".format(str(e))

        return 200, "ok"

    # 收货
    def receive_book(self, user_id: str, order_id: str):
        try:
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id)

            row = self.session.query(store.HistoryOrder).filter_by(order_id=order_id).first()
            if row is None:
                return error.error_invalid_order_id(order_id)

            is_cancelled = row.is_cancelled
            if is_cancelled is True:
                return error.error_order_cancelled(order_id)
            is_delivered = row.is_delivered
            if is_delivered is False:
                return error.error_order_not_delivered(order_id)

            # 更新历史订单状态为已收货
            rowcount = self.session.query(store.HistoryOrder).filter_by(order_id=order_id).update(
                {'is_delivered': True}
            )
            if rowcount == 0:
                return error.error_invalid_order_id(order_id)
            self.session.commit()

        except Exception as e:
            return 530, "{}".format(str(e))

        return 200, "ok"

    # 买家主动取消订单
    def buyer_cancel_order(self, user_id: str, order_id: str):
        try:
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id)

            rows = self.session.query(store.HistoryOrder).filter_by(order_id=order_id).all()
            if rows is None:
                return error.error_invalid_order_id(order_id)

            for order in rows:
                is_cancelled = order.is_cancelled
                if is_cancelled is True:
                    return error.error_order_cancelled(order_id)
                # 订单状态为已支付时无法取消订单
                is_paid = order.is_paid
                if is_paid is True:
                    return error.error_order_cancellation_fail(order_id)
                self.cancel_order(order, order_id)

            self.session.commit()

        except Exception as e:
            return 530, "{}".format(str(e))

        return 200, "ok, order cancelled"

    # 超时自动取消订单
    def overtime_cancel_order(self):
        try:
            living_time = 15 * 60  # 未支付订单保留15分钟
            rows = self.session.query(store.HistoryOrder).all()
            num_rows = len(rows)
            # 还没有产生订单
            if num_rows == 0:
                return 200, "ok"

            num_cancelled = 0

            for order in rows:
                order_id = order.order_id
                is_cancelled = order.is_cancelled
                is_paid = order.is_paid
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

            self.session.commit()

        except Exception as e:
            return 530, "{}".format(str(e))

        return 200, "ok, {} orders cancelled".format(num_cancelled)

    # 取消订单
    def cancel_order(self, order, order_id):
        self.session.query(store.HistoryOrder).filter_by(order_id=order_id).update(
            {'is_cancelled': True}
        )
        # 还原书籍库存
        self.session.query(store.StoreTable).filter_by(store_id=order.store_id, book_id=order.book_id).update(
            {'stock_level': store.StoreTable.stock_level + order.book_count}
        )
        # 删除new_order和new_order_detail中的相关文档
        rowcount = self.session.query(store.NewOrder).filter_by(order_id=order_id).delete()
        if rowcount == 0:
            return error.error_invalid_order_id(order_id)

        rowcount = self.session.query(store.NewOrderDetail).filter_by(order_id=order_id).delete()
        if rowcount == 0:
            return error.error_invalid_order_id(order_id)

        self.session.commit()

    # 搜索历史订单
    def search_history_order(self, user_id, order_id, page, per_page):
        try:
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id)

            if order_id == "":
                row = self.session.query(store.HistoryOrder).filter_by(user_id=user_id).all()
                num_row = len(row)
                if num_row == 0:
                    return error.error_non_history_order(user_id)
                results = row

                if num_row > per_page:
                    start = (page - 1) * per_page
                    end = start + per_page
                    if end > num_row:
                        results = row[-per_page:]
                    else:
                        results = row[start:end]

                res = []
                for result in results:
                    res.append((
                        f"order_id: {result.order_id}\n"
                        f"user_id: {result.user_id}\n"
                        f"store_id: {result.store_id}\n"
                        f"book_id: {result.book_id}\n"
                        f"book_count: {result.book_count}\n"
                        f"price: {result.price}\n"
                        f"is_cancelled: {result.is_cancelled}\n"
                        f"is_paid: {result.is_paid}\n"
                        f"is_delivered: {result.is_delivered}\n"
                        f"is_received: {result.is_received}\n"
                    ))

            else:
                row = self.session.query(store.HistoryOrder).filter_by(order_id=order_id, user_id=user_id).all()
                num_row = len(row)
                if num_row == 0:
                    return error.error_non_history_order(user_id)
                results = row

                if num_row > per_page:
                    start = (page - 1) * per_page
                    end = start + per_page
                    if end > num_row:
                        results = row[-per_page:]
                    else:
                        results = row[start:end]

                res = []
                for result in results:
                    res.append((
                        f"order_id: {result.order_id}\n"
                        f"user_id: {result.user_id}\n"
                        f"store_id: {result.store_id}\n"
                        f"book_id: {result.book_id}\n"
                        f"book_count: {result.book_count}\n"
                        f"price: {result.price}\n"
                        f"is_cancelled: {result.is_cancelled}\n"
                        f"is_paid: {result.is_paid}\n"
                        f"is_delivered: {result.is_delivered}\n"
                        f"is_received: {result.is_received}\n"
                    ))

            self.session.commit()
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
                rows = self.session.query(store.StoreTable).filter_by(store_id=store_id).all()
                if len(rows) == 0:
                    return error.error_non_exist_store_id(store_id)

                book_id_store = []
                for row in rows:
                    book_id_store.append(row.book_id)

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

                self.session.commit()
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

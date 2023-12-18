from be.model import store


class DBConn:
    def __init__(self):
        self.session, self.textdb = store.get_db_conn()

    def user_id_exist(self, user_id):
        row = self.session.query(store.User).filter_by(user_id=user_id).first()
        if row is None:
            return False
        else:
            return True

    def book_id_exist(self, store_id, book_id):
        row = self.session.query(store.StoreTable).filter_by(store_id=store_id, book_id=book_id).first()
        if row is None:
            return False
        else:
            return True

    def store_id_exist(self, store_id):
        row = self.session.query(store.UserStore).filter_by(store_id=store_id).first()
        if row is None:
            return False
        else:
            return True

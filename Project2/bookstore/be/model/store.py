import logging
import pymongo
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


Base = declarative_base()


class User(Base):
    __tablename__ = 'user'

    user_id = Column(String, primary_key=True, unique=True, nullable=False)
    password = Column(String, nullable=False)
    balance = Column(Integer, nullable=False)
    token = Column(String)
    terminal = Column(String)


class UserStore(Base):
    __tablename__ = 'user_store'

    user_id = Column(String, ForeignKey('user.user_id'), primary_key=True, nullable=False)
    store_id = Column(String, primary_key=True, nullable=False)


class StoreTable(Base):
    __tablename__ = 'store'

    store_id = Column(String, primary_key=True, nullable=False)
    book_id = Column(String, primary_key=True, nullable=False)
    book_info = Column(String)
    stock_level = Column(Integer)


class NewOrder(Base):
    __tablename__ = 'new_order'

    order_id = Column(String, primary_key=True, unique=True, nullable=False)
    user_id = Column(String, ForeignKey('user.user_id'))
    store_id = Column(String)


class NewOrderDetail(Base):
    __tablename__ = 'new_order_detail'

    order_id = Column(String, primary_key=True, nullable=False)
    book_id = Column(String, primary_key=True, nullable=False)
    count = Column(Integer)
    price = Column(Integer)


class HistoryOrder(Base):
    __tablename__ = 'history_order'

    order_id = Column(String, primary_key=True, nullable=False)
    store_id = Column(String)
    user_id = Column(String, primary_key=True, nullable=False)
    book_id = Column(String)
    book_count = Column(Integer)
    price = Column(Integer)
    is_cancelled = Column(Boolean)
    is_paid = Column(Boolean)
    is_delivered = Column(Boolean)
    is_received = Column(Boolean)


class BookDetail(Base):
    __tablename__ = 'book_detail'

    book_id = Column(String, primary_key=True, unique=True, nullable=False)
    title = Column(String)
    author = Column(String)
    book_intro = Column(String)
    content = Column(String)
    tags = Column(String)


class Store:
    database: str

    def __init__(self):
        self.session = None
        self.database = "be"
        self.engine = create_engine('postgresql://postgres:longyifei1206@localhost:5432/be',
                                    echo=True, pool_size=8, pool_recycle=60*30)

        self.init_tables()

    def init_tables(self):
        try:
            Base.metadata.create_all(self.engine)

        except Exception as e:
            logging.error(e)

    def get_db_conn(self):
        DbSession = sessionmaker(bind=self.engine)
        self.session = DbSession()
        return self.session


database_instance: Store = None


def init_database():
    global database_instance
    database_instance = Store()


def get_db_conn():
    global database_instance
    return database_instance.get_db_conn()

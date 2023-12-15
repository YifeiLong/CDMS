import pytest
import time

from fe.test.gen_book_data import GenBook
from fe.access.new_buyer import register_new_buyer
from fe.access import auth, buyer
from fe import conf
import uuid


class TestSearchBook:
    @pytest.fixture(autouse=True)
    def pre_run_initialization(self):
        self.seller_id = "test_search_book_seller_id_{}".format(time.time())
        # self.seller_id = "Jason"
        self.store_id = "test_search_book_store_id_{}".format(time.time())
        # self.store_id = "store1"
        self.buyer_id = "test_search_book_buyer_id_{}".format(time.time())
        # self.buyer_id = "Jack"
        self.password = self.buyer_id
        gen_book = GenBook(self.seller_id, self.store_id)
        ok, buy_book_id_list = gen_book.gen(
            non_exist_book_id=False, low_stock_level=False, max_book_count=5
        )
        self.buy_book_info_list = gen_book.buy_book_info_list
        assert ok
        # self.auth = auth.Auth(conf.URL)
        # code = self.auth.register(self.buyer_id, self.password)
        b = register_new_buyer(self.buyer_id, self.password)
        self.buyer = b
        # code, _ = self.buyer.new_order(self.store_id, buy_book_id_list)
        # assert code == 200
        yield

    def test_ok(self):
        code = self.buyer.search_book(store_id=self.store_id, title="", author="", book_intro="", content="", tags=[])
        assert code == 200

    def test_non_search_result(self):
        code = self.buyer.search_book(store_id="", title="", author="三毛_x", book_intro="", content="", tags=[])
        assert code != 200

    def test_non_exist_store_id(self):
        code = self.buyer.search_book(store_id=self.store_id + "_x", title="", author="三毛", book_intro="", content="", tags=[])
        assert code != 200

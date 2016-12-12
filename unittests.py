import unittest
import random

from main import app
from flask_api import status

from consts import *
from models import *

db.app = app
db.init_app(app)
db.create_all()

# generate random data
xs = range(1, 1000)
random.shuffle(xs)
ys = range(1, 1000)
random.shuffle(ys)

class TestDB(unittest.TestCase):
	"""
	Unittests for DB
	"""

	def _assertValidStats(self, stats, testdata):
		"""
		Compare DB stats and list stats
		"""
		xlist, ylist = zip(*testdata)
		self.assertEquals(stats.minX, min(xlist))
		self.assertEquals(stats.minY, min(ylist))
		self.assertEquals(stats.maxX, max(xlist))
		self.assertEquals(stats.maxY, max(ylist))
		self.assertEquals(stats.sumX, sum(xlist))
		self.assertEquals(stats.sumY, sum(ylist))
		self.assertEquals(stats.count, len(testdata))

	def testDBUser(self):
		"""
		Try to create record in a table DBUser
		"""
		user = DBUser(x = xs.pop(), y = ys.pop())
		db.session.add(user)
		db.session.commit()

	def testDBUserStats(self):
		"""
		Generate test data and validate DBUserStats
		"""
		# Generate testdata from random sequences
		testdata = [(xs.pop(), ys.pop()) for i in range(SQL_TESTDATA_COUNT)]

		# Fill table User with testdata
		DBUser.query.delete()
		for x, y in testdata:
			user = DBUser(x, y)
			db.session.add(user)
		db.session.commit()

		# Get stats from DB and validate them
		stats = DBUserStats()
		self._assertValidStats(stats, testdata)

		# Test stats with limits
		# Cut testdata for that
		sorted_x, sorted_y = map(sorted, zip(*testdata))
		cut_index = SQL_TESTDATA_COUNT / 5
		offsetX = sorted_x[cut_index]
		offsetY = sorted_y[cut_index]
		limitX = sorted_x[-cut_index]
		limitY = sorted_y[-cut_index]
		testdata = [
			(x, y) for x, y in testdata \
			if y <= limitY and y >= offsetY and \
			x <= limitX and x >= offsetX
		]

		# Get stats from DB and validate them
		stats = DBUserStats(offsetX, offsetY, limitX, limitY)
		self._assertValidStats(stats, testdata)

class TestUserList(unittest.TestCase):
	"""
	Unittests for UserList
	"""
	def setUp(self):
		self.client = app.test_client()
		self.url = "%s/users" % BASEURL
		# lambda to generate random unique coordinates
		self.getCoords = lambda: (xs.pop(), ys.pop())

	def testAddUser(self):
		"""
		Try to add new user
		Check return code is 201
		"""
		res = self.client.post(self.url, data = '{"x": %s, "y": %s}' % self.getCoords())
		self.assertEquals(res.status_code, status.HTTP_201_CREATED)

	def testAddInvalidUser(self):
		"""
		Try to add new user without x or y
		Check return code is 400
		"""
		res = self.client.post(self.url, data = '{"x": %s}' % xs.pop())
		self.assertEquals(res.status_code, status.HTTP_400_BAD_REQUEST)
		res = self.client.post(self.url, data = '{"y": %s}' % ys.pop())
		self.assertEquals(res.status_code, status.HTTP_400_BAD_REQUEST)

	def testAddiExistedUser(self):
		"""
		Try to add new existed user
		Check return code is 409
		"""
		coords = self.getCoords()
		self.client.post(self.url, data = '{"x": %s, "y": %s}' % coords)
		res = self.client.post(self.url, data = '{"x": %s, "y": %s}' % coords)
		self.assertEquals(res.status_code, status.HTTP_409_CONFLICT)

	def testEmptyUserList(self):
		"""
		Try to get empty UserList
		Check return code is 400
		"""
		DBUser.query.delete()
		res = self.client.get(self.url)
		self.assertEquals(res.status_code, status.HTTP_404_NOT_FOUND)

	def testFullUserList(self):
		"""
		Try to get UserList
		Check return code is 200
		"""
		self.client.post(self.url, data = '{"x": %s, "y": %s}' % self.getCoords())
		res = self.client.get(self.url)
		self.assertEquals(res.status_code, status.HTTP_200_OK)

	def testUserListPages(self):
		"""
		Remove all data, generate 10 records.
		Try to show data for page=1 with pagesize=9
		Result code 200 is expected
		Then try to move over maximum
		with page=0, pagesize=10 and page=2, pagesize=9
		Result code 404 is expected
		"""
		DBUser.query.delete()
		for i in range(10):
			self.client.post(self.url, data = '{"x": %s, "y": %s}' % self.getCoords())

		url_params = "?page=1&pagesize=9"
		res = self.client.get(self.url + url_params)
		self.assertEquals(res.status_code, status.HTTP_200_OK)

		url_params = "?page=2&pagesize=9"
		res = self.client.get(self.url + url_params)
		self.assertEquals(res.status_code, status.HTTP_404_NOT_FOUND)

		url_params = "?page=1&pagesize=10"
		res = self.client.get(self.url + url_params)
		self.assertEquals(res.status_code, status.HTTP_404_NOT_FOUND)

class TestUser(unittest.TestCase):
	"""
	Unittests for User: get, update, delete
	"""

	def setUp(self):
		self.client = app.test_client()
		self.url = "%s/users" % BASEURL
		self.getCoords = lambda: (xs.pop(), ys.pop())

	def _get_user_url(self, user_id):
		return "%s/%s" % (self.url, user_id)

	def _create_db_user(self):
		"""
		Create DB user and return user object
		"""
		x, y = self.getCoords()
		user = DBUser(x = x, y = y)
		db.session.add(user)
		db.session.flush()
		db.session.commit()
		return user

	def testGetUser(self):
		"""
		Add user into DB, try to get it by id: 200 is expected
		After that try to get user by id + 100: 404 is expected
		"""
		user = self._create_db_user()
		res = self.client.get(self._get_user_url(user.id))
		self.assertEquals(res.status_code, status.HTTP_200_OK)
		res = self.client.get(self._get_user_url(user.id + 100))
		self.assertEquals(res.status_code, status.HTTP_404_NOT_FOUND)

	def testUpdateUser(self):
		"""
		Check parameters might be updated one by one
		Compare updated parameters with old ones
		Validate that request without parameters is invalid
		"""
		user = self._create_db_user()
		user_id = user.id
		url = self._get_user_url(user_id)
		old_x, old_y = user.x, user.y

		res = self.client.post(url, data = '{"x": %s}' % xs.pop())
		self.assertEquals(res.status_code, status.HTTP_200_OK)
		res = self.client.post(url, data = '{"y": %s}' % ys.pop())
		self.assertEquals(res.status_code, status.HTTP_200_OK)
		res = self.client.post(url, data = '{}')
		self.assertEquals(res.status_code, status.HTTP_400_BAD_REQUEST)

		user = DBUser.query.filter_by(id = user_id).one()
		self.assertNotEqual(old_x, user.x)
		self.assertNotEqual(old_y, user.y)

	def testDeleteUser(self):
		"""
		Add new user in DB and delete it with API
		Check there is no such user in DB anymore
		"""
		user = self._create_db_user()
		user_id = user.id
		url = self._get_user_url(user_id)
		res = self.client.delete(url)
		self.assertEquals(res.status_code, status.HTTP_200_OK)

		user = DBUser.query.filter_by(id = user_id).first()
		self.assertIsNone(user)

class TestInfo(unittest.TestCase):
	"""
	Unittests for Info
	"""
	def setUp(self):
		self.client = app.test_client()
		self.url = "%s/users/info" % BASEURL

	def testGetInfo(self):
		"""
		Try to get info
		Check return code is 200
		"""
		res = self.client.get(self.url)
		self.assertEquals(res.status_code, status.HTTP_200_OK)

class TestKnn(unittest.TestCase):
	"""
	Unittests for Knn
	"""
	def setUp(self):
		self.radius = 10
		self.user_id = 10
		self.client = app.test_client()
		self.url = "%s/users/knn" % BASEURL

	def testGetKnn(self):
		"""
		Check request without mandatory arguments
		Check Knn return 200 with mandatory arguments
		"""
		Rarg = "R=%s" % self.radius
		Uarg = "U=%s" % self.user_id
		for arg in (Rarg, Uarg):
			res = self.client.get("%s?%s" % (self.url, arg))
			self.assertEquals(res.status_code, status.HTTP_400_BAD_REQUEST)

		res = self.client.get("%s?%s&%s" % (self.url, Rarg, Uarg))
		self.assertEquals(res.status_code, status.HTTP_200_OK)

if __name__ == "__main__":
	suites = list()
	for test in (TestDB, TestUserList, TestUser, TestInfo, TestKnn):
		suites.append(unittest.TestLoader().loadTestsFromTestCase(test))
	suite = unittest.TestSuite(suites)
	results = unittest.TextTestRunner(verbosity = 2).run(suite)

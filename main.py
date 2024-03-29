from math import sqrt
import os
import sys

from flask import Flask, request
from flask_api import status
from flask_restful import Resource, Api

from consts import *
from models import *

app = Flask("NN")
# Load config for app
if __name__ == '__main__':
	app.config.from_object('consts.ProductionConfig')
	# re-create DB to not conflict with old data
	if os.path.exists(DBFile):
		os.unlink(DBFile)
elif sys.argv[0] == "benchmark.py":
	app.config.from_object('consts.BenchmarkConfig')
else:
	app.config.from_object('consts.TestingConfig')
# Catch all unexpected 404s in json format
api = Api(app, catch_all_404s = True)

# Init DB
db.app = app
db.init_app(app)
db.create_all()

class Info(Resource):
	"""
	Provide information about Users
	Example:
		http://127.0.0.1:5000/v1/NN/users/info -X GET
	"""

	def get(self):
		user_count = DBUser.query.count()
		return {
			"message": "OK",
			"user_count": user_count
		}, status.HTTP_200_OK

class UserList(Resource):
	"""
	Controller to show and extend userlist
	If user exists return 409 Conflict 
	Example:
		curl http://127.0.0.1:5000/v1/NN/users -X POST -d '{"x": 1, "y": 2}'
		curl http://127.0.0.1:5000/v1/NN/users?page=2&pagesize=5 -X GET
	"""

	def get(self):
		"""
		Get user list
		By default show only first 100 records
		page and pagesize are configurable by request args
		"""
		page = int(request.args.get('page', 0))
		pagesize = int(request.args.get('pagesize', 100))
		query = DBUser.query
		query = query.offset(page * pagesize)
		query = query.limit(pagesize)
		users = query.all()
		if not users:
			return {
				"message": "Users not found"
			}, status.HTTP_404_NOT_FOUND

		# Create json for each user in list
		json_users = dict()
		for user in users:
			json_users[user.id] = {
				"x": user.x,
				"y": user.y,
				"user_url": "%s/%s" %(request.url, user.id)
			}

		return {
			"message": "OK",
			"users": json_users
		}, status.HTTP_200_OK

	def post(self):
		"""
		Fetch json data from body ignoring Content-Type header by force flag
		If body is not json flask restfull api automatically handles that
		Store new user in DB and return user url
		"""
		json_data = request.get_json(force = True)
		if "x" not in json_data or "y" not in json_data:
			return {
				"message": "Bad request. x and y keys are requied."
			}, status.HTTP_400_BAD_REQUEST

		x = json_data["x"]
		y = json_data["y"]

		# Check user exists. If so, return conflict
		user = DBUser.query.filter_by(x = x, y = y).first()
		if user:
			return {
				"message": "Conflict. User (%s, %s) exists" % (x, y),
			}, status.HTTP_409_CONFLICT
		# Add user into DB
		user = DBUser(x, y)
		db.session.add(user)
		db.session.flush()

		db.session.commit()
		# Get user ID and return url
		return {
			"message": "Created",
			"user_url": "%s/%s" %(request.url, user.id)
		}, status.HTTP_201_CREATED

class User(Resource):
	"""
	Controller for other user CRUD actions
	Example:
		curl http://127.0.0.1:5000/v1/NN/users/id -X GET
		curl http://127.0.0.1:5000/v1/NN/users/id -X POST -d '{"x": 4}'
		curl http://127.0.0.1:5000/v1/NN/users/id -X DELETE
	"""

	def _not_found_error(self, user_id):
		return {
			"message": "User %s not found" % user_id
		}, status.HTTP_404_NOT_FOUND

	def get(self, user_id):
		"""
		Return User object
		"""
		user = DBUser.query.filter_by(id = user_id).first()
		if not user:
			return self._not_found_error(user_id)
		return {
			"message": "OK",
			"x": user.x,
			"y": user.y
		}, status.HTTP_200_OK
		
	def post(self, user_id):
		"""
		Update User object
		"""
		user = DBUser.query.filter_by(id = user_id).first()
		if not user:
			return self._not_found_error(user_id)
		json_data = request.get_json(force = True)
		if "x" not in json_data and "y" not in json_data:
			return {
				"message": "Bad request. x or y keys are requied."
			}, status.HTTP_400_BAD_REQUEST

		x = json_data.get("x")
		y = json_data.get("y")
		if x:
			user.x = x
		if y:
			user.y = y
		db.session.flush()
		db.session.commit()
		return {
			"message": "OK",
			"user_url": "%s/%s" %(request.url, user.id)
		}, status.HTTP_200_OK
		
	def delete(self, user_id):
		"""
		Delete User object
		"""
		query = DBUser.query.filter_by(id = user_id)
		user = query.first()
		if not user:
			return self._not_found_error(user_id)
		query.delete()
		db.session.commit()
		return {
			"message": "OK"
		}, status.HTTP_200_OK

class Knn(Resource):
	"""
	Controller to find K nearest neighbors
	R (raduis) and U (user_id) arguments are mandatory
	Example:
		curl http://127.0.0.1:5000/v1/NN/users/knn?U=10&R=10 -X GET
	"""
	def __init__(self):
		"""
		Initial conditions:
		- user coord
		- radius
		"""
		self.x0 = None
		self.y0 = None
		self.r = None

	def getMinMaxRectDist(self, stats):
		"""
		Returns min and max distances from point to rectangle
		"""
		dists = list()

		# Add rect coner distances
		for x, y in stats.rect:
			dist = sqrt((self.x0 - x) ** 2 + (self.y0 - y) ** 2)
			dists.append(dist)

		# Add rect side distances
		if (stats.minX <= self.x0 <= stats.maxX):
			for y in (stats.minY, stats.maxY):
				dist = abs(y - self.y0)
				dists.append(dist)
		if (stats.minY <= self.y0 <= stats.maxY):
			for x in (stats.minX, stats.maxX):
				dist = abs(x - self.x0)
				dists.append(dist)

		return min(dists), max(dists)

	def getDistkNN(self, stats):
		"""
		Algorythm by comparing all distances with radius
		Used in benchmark test
		"""
		result = 0
		for user in DBUser.query.yield_per(100):
			dist = sqrt((user.x - self.x0) ** 2 + (user.y - self.y0) ** 2)
			if dist <= self.r:
				result += 1
		return result

	def getkNN(self, stats):
		"""
		=== Main algorythm ===
		If rect small enough (side < R/10) or
		amount of users is small enogh check all distances
		and return users count inside the search zone
		Check rect and the search zone
			- If outside return 0
			- If inside return rect user count
			- If has intersections:
			split into two rect and apply the same algorythm
		Intersections logic:
			- Find min and max distance from initial user to rect
			- Compare distance with R
		Split logic:
			- Split longer rect side.
			- Split by neighbors of avarage value
		"""
		result = 0
		if stats.count == 0:
			return 0

		# Check rectangle is outside, inside or has intersections
		min_dist, max_dist = self.getMinMaxRectDist(stats)
		if (min_dist > self.r) and (max_dist > self.r):
			# Rect outside
			return 0
		elif (min_dist <= self.r) and (max_dist <= self.r):
			# Rect inside
			return stats.count

		# Intersection between rectangle and search area
		if (stats.maxX - stats.minX) < self.r / 10 \
						or (stats.maxY - stats.minY) < self.r \
						or stats.count < MIN_USERS:
			# In case of small amount of users, calculate distances manually
			# In case of small rect side, calculate distances manually
			users = DBUser.query.filter(\
				DBUser.x >= stats.minX, \
				DBUser.x <= stats.maxX, \
				DBUser.y >= stats.minY, \
				DBUser.y <= stats.maxY).all()
			for user in users:
				dist = sqrt((self.x0 - user.x) ** 2 + (self.y0 - user.y) ** 2)
				if dist <= self.r:
					result += 1
		else:
			# Split rect into two in longer side
			if abs(stats.maxX - stats.minX) >= abs(stats.maxY - stats.minY):
				# find nearest left and right of avgX
				leftX = DBUser.query.filter(DBUser.x <= stats.avgX).order_by(db.desc(DBUser.x)).first().x
				rightX = DBUser.query.filter(DBUser.x > stats.avgX).order_by(DBUser.x).first().x
				stats1 = DBUserStats(stats.minX, stats.minY, leftX, stats.maxY)
				stats2 = DBUserStats(rightX, stats.minY, stats.maxX, stats.maxY)
			else:
				# find nearest left and right of avgY
				downY = DBUser.query.filter(DBUser.y <= stats.avgY).order_by(db.desc(DBUser.y)).first().y
				upY = DBUser.query.filter(DBUser.y > stats.avgY).order_by(DBUser.y).first().y
				stats1 = DBUserStats(stats.minX, stats.minY, stats.maxX, downY)
				stats2 = DBUserStats(stats.minX, upY, stats.maxX, stats.maxY)
			result += self.getkNN(stats1)
			result += self.getkNN(stats2)

		return result

	def get(self):
		"""
		Return result of kNN algorythm
		R and U arguments are mandatory
		"""
		r = int(request.args.get('R', 0))
		user_id = int(request.args.get('U', 0))
		dist_angorythm = request.args.get('dist', None)
		if not r:
			return {
				"message": "Bad request. R argument is required."
			}, status.HTTP_400_BAD_REQUEST
		if not user_id:
			return {
				"message": "Bad request. U argument is required."
			}, status.HTTP_400_BAD_REQUEST

		u = DBUser.query.filter_by(id = user_id).first()
		if not u:
			return {
				"message": "User %s not found" % user_id
			}, status.HTTP_404_NOT_FOUND

		dstats = DBUserStats()
		nnstats = DBUserStats(u.x - r, u.y - r, u.x + r, u.y + r)
		init_rect = (
			max(dstats.minX, nnstats.minX),
			max(dstats.minY, nnstats.minY),
			min(dstats.maxX, nnstats.maxX),
			min(dstats.maxY, nnstats.maxY),
		)
		init_stats = DBUserStats(*init_rect)

		self.x0, self.y0 = (u.x, u.y)
		self.r = r

		if dist_angorythm == "Y":
			result = self.getDistkNN(init_stats) - 1
		else:
			result = self.getkNN(init_stats) - 1

		return {
			"message": "OK",
			"result": result,
		}, status.HTTP_200_OK

api.add_resource(UserList, "%s/users" % BASEURL)
api.add_resource(Info, "%s/users/info" % BASEURL)
api.add_resource(User, "%s/users/<int:user_id>" % BASEURL)
api.add_resource(Knn, "%s/users/knn" % BASEURL)

if __name__ == '__main__':
	app.run(debug = True)

'''
Utility functions
'''

import pprint
import json
from pymongo import MongoClient
import logging

import argparse
from argparse import ArgumentParser
from bson import json_util
from bson import BSON
from pymongo.errors import BulkWriteError
from pymongo import InsertOne, DeleteOne, ReplaceOne, UpdateOne

# TODO : add time of creation/update
# Metadata db
def add_to_metadatadb(sender, replica_ip, location, indices, verbose=True):
	record = {}
	record["replica_ip"] = replica_ip
	record["location"] = location
	record["indices"] = indices

	client = MongoClient('localhost', 27017)
	if sender == 'master':
		db = client.masterdb
	elif sender == 'backup':
		db = client.backupdb
	else:
		db = client[sender+"db"]

	metadata_coll = db.metadata
	# unique index

	metadata_coll.create_index( "location", unique = True)

	try:
		metadata_coll.update_one({"location" : location}, {"$set": {"location" : location,  "replica_ip" : replica_ip, "indices" : list(indices)}} , upsert=True)
		if(verbose):
			print "Success"
			print "Added ", str(record)," to metadata of ",sender 
	except Exception as e:
		print "Failed due to ", str(e)


def query_metadatadb_indices(sender, location):
	client = MongoClient('localhost', 27017)
	if sender == 'master':
		db = client.masterdb
	elif sender == 'backup':
		db = client.backupdb
	else:
		db = client[sender+"db"]
	
	entry = db.metadata.find_one({'location' : location})

	words = []
	if entry is not None:
		for word in entry['indices']:
			words.append(word)
	client.close()
	return words

def update_replica_ip(sender, location, new_replica_ip):
	client = MongoClient('localhost', 27017)
	if sender == 'master':
		db = client.masterdb
	elif sender == 'backup':
		db = client.backupdb
	else:
		db = client[sender+"db"]
	
	try:
		db.metadata.update_one({"location" : location}, {"$set": {"replica_ip" : new_replica_ip}} , upsert=True)
	except Exception as e:
		print "Failed due to ", str(e)
	client.close()

def get_replica_ips_locs_from_metadatadb(sender):
	client = MongoClient('localhost', 27017)
	if sender == 'master':
		db = client.masterdb
	elif sender == 'backup':
		db = client.backupdb
	else:
		db = client[sender+"db"]

	responses = db.metadata.find({}, {'replica_ip':1, 'location':1, '_id':0})
	client.close()
	result = []
	for response in responses:
		result.append((response["replica_ip"], response["location"]))
	return result

def query_metadatadb(sender, location, search_terms):
	client = MongoClient('localhost', 27017)
	if sender == 'master':
		db = client.masterdb
	elif sender == 'backup':
		db = client.backupdb
	else:
		db = client[sender+"db"]
	
	metadata_coll = db.metadata
	replica = metadata_coll.find_one({"location":location})
	if replica is None:
		return None, False

	status = True
	for search_term in search_terms:
		if search_term not in list(replica["indices"]):
			status = False
			break

	return replica["replica_ip"], status


def get_similar(sender, words):
	client = MongoClient('localhost', 27017)
	if sender == 'master':
		db = client.masterdb
	elif sender == 'backup':
		db = client.backupdb
	else:
		db = client[sender+"db"]

	indices = db.indices
	responses = indices.find({"status" : "committed", "name" :{"$in": words}})
	client.close()

	similar = set()
	if responses is not None:
		for response in responses:
			similar.update(response["sim_words"])
		
	return list(similar)

def get_data_for_indices(sender, indices):
	indices = get_similar(sender, indices)

	client = MongoClient('localhost', 27017)
	if sender == 'master':
		db = client.masterdb
	elif sender == 'backup':
		db = client.backupdb
	else:
		db = client[sender+"db"]

	indices_coll = db.indices
	# print indices, len(indices)
	responses = indices_coll.find({"status" : "committed", "name" :{"$in": indices}})
	# print "Works till here"
	result =  json_util.dumps(responses)
	# print "Here too"
	return result, indices




def querydb(sender, search_term):
	'''Query on mongodb database for suitable response for search term
	'''
	client = MongoClient('localhost', 27017)
	if sender == 'master':
		db = client.masterdb
	elif sender == 'backup':
		db = client.backupdb
	else:
		db = client[sender+"db"]

	print "Searching ", sender
	indices = db.indices
	response = indices.find_one({"status" : "committed", "name" : search_term})
	client.close()
	if response is not None:
		return response["urls"]
	return []

def getallwords(sender):
	'''Query on mongodb database for all name words
	'''
	client = MongoClient('localhost', 27017)
	if sender == 'master':
		db = client.masterdb
	elif sender == 'backup':
		db = client.backupdb
	else:
		db = client[sender+"db"]

	indices = db.indices
	responses = indices.find({}, {'name':1, '_id': 0})
	client.close()

	words = []
	if responses is not None:
		for response in responses:
			words.append(response['name'])

	return words

def addtodb(sender, data):
	'''Add json string to db
	'''
	client = MongoClient('localhost', 27017)
	if sender == 'master':
		db = client.masterdb
	elif sender == 'backup':
		db = client.backupdb
	else:
		db = client[sender+"db"]

	print "Adding to DB"
	if type(data) != type(list()):
		data = json.loads(data.decode('string-escape').strip('"'))
	indices = db.indices
	
	requests = []
	for rec in data:
		# print rec
		requests.append(UpdateOne({"name" : rec["name"]}, {"$set": {"status" :"committed", "name" : rec["name"], "urls" : rec["urls"], "sim_words" : rec["sim_words"], "is_new" : 1}} , upsert=True))
	
	if len(requests) == 0:
		return True

	try:
		result = indices.bulk_write(requests, ordered=False)
	except BulkWriteError as exc:
		print "Error: ", exc.details
	
	print "Records: ", indices.count()
	client.close()
	return True

def removefromdb(sender, data):
	client = MongoClient('localhost', 27017)
	if sender == 'master':
		db = client.masterdb
	elif sender == 'backup':
		db = client.backupdb
	else:
		db = client[sender+"db"]
	
	indices = db.indices
	indices.remove({'name':{'$in': data}})

	client.close()
	return True

def commitdb(sender):
	client = MongoClient('localhost', 27017)
	if sender == 'master':
		db = client.masterdb
	elif sender == 'backup':
		db = client.backupdb
	else:
		db = client[sender+"db"]

	print "COMMIT"
	indices = db.indices

	# remove duplicate records whose status is committed and who have names in the pending list
	words = indices.find({"status" : "pending"}, {"name" : 1, '_id' : 0})
	words = [x['name'] for x in words]
	print "Duplicates : ",words
	status = indices.remove({"status" : "committed", "name" :{"$in": words}})
	print status
	
	# update pending records to committed
	status = indices.update({'status': 'pending'},
          {'$set': {'status':'committed'}}, 
          multi=True)
	print "Write status ", status
	print "Total length of documents ", indices.count()
	client.close()


def rollbackdb(sender):
	client = MongoClient('localhost', 27017)
	if sender == 'master':
		db = client.masterdb
	elif sender == 'backup':
		db = client.backupdb
	else:
		db = client[sender+"db"]

	print "ROLLBACK"
	indices = db.indices
	status = indices.delete_many({'status' : 'pending'})
	print status
	client.close()


def init_logger(db_name, logging_level):
	logger = logging.getLogger(db_name)
	logger.setLevel(logging_level)
	# add handler only if already added
	if not len(logger.handlers):
		fh = logging.FileHandler('log'+db_name+'.log')
		fh.setLevel(logging_level)
		# create a logging format
		formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
		fh.setFormatter(formatter)
		logger.addHandler(fh)
	return logger


def parse_level(level):
	if level == 'DEBUG':
		logging_level = logging.DEBUG
	elif level == 'INFO':
		logging_level = logging.INFO
	elif level == 'WARNING':
		logging_level = logging.WARNING
	elif level == 'ERROR':
		logging_level = logging.ERROR
	elif level == 'CRITICAL':
		logging_level = logging.CRITICAL
	else:
		message = 'Invalid choice! Please choose from DEBUG, INFO, WARNING, ERROR, CRITICAL'
		argparse.ArgumentError(self, message)
	return logging_level

def read_replica_filelist():
	f = open("replicas_list.txt")
	replica_ips = {}
	for line in f:
		line = line.strip().split()
		# IP LOCATION
		location = line[1].strip()
		ip = line[0].strip()
		if location not in replica_ips:
			replica_ips[location] = []
		replica_ips[location].append(ip)
	return replica_ips

def get_all_replica_ips(sender):
	client = MongoClient('localhost', 27017)
	if sender == 'master':
		db = client.masterdb
	elif sender == 'backup':
		db = client.backupdb
	else:
		db = client[sender+"db"]
	
	entry = db.metadata.find({})

	replica_ips = []
	
	if entry is not None:
		for replica in entry:
			# print replica
			replica_ips.append(replica["replica_ip"])
	client.close()
	return replica_ips

def get_data_for_replica(sender, replica_ip):
	# return get_data_for_indices('master', ["freakish"])
	
	# location, replica_ip, indices
	client = MongoClient('localhost', 27017)
	if sender == 'master':
		db = client.masterdb
	else:
		db = client.backupdb
	
	metadata_coll = db.metadata
	indices_coll = db.indices
	replica = metadata_coll.find_one({"replica_ip":replica_ip})
	
	indices = replica["indices"]

	# for indice 
	# print indices, len(indices)
	responses = indices_coll.find({"is_new" : 1, "name" :{"$in": indices}})
	result_cur = [response for response in responses]
	indices = [result["name"] for result in result_cur]
	result =  json_util.dumps(result_cur)
	return result, indices

	
def get_data_for_backup(sender):
	# return get_data_for_indices('master', ["freakish"])
	
	client = MongoClient('localhost', 27017)
	if sender == 'master':
		db = client.masterdb
	else:
		db = client.backupdb
	indices_coll = db.indices
	indices = []
	
	responses = indices_coll.find({"is_new" : 1})
	# print responses, responses.count()
	result_cur = [response for response in responses]
	indices = [result["name"] for result in result_cur]
	result =  json_util.dumps(result_cur)
	return result, indices

def updateMasterIndices(sender, data):
	client = MongoClient('localhost', 27017)
	if sender == 'master':
		db = client.masterdb
	elif sender == 'backup':
		db = client.backupdb
	else:
		db = client[sender+"db"]

	if type(data) != type(list(data)):
		data = json.loads(data.decode('string-escape').strip('"'))
	indices_coll = db.indices

	requests = []
	for rec in data:
		# print rec
		requests.append(UpdateOne({"name" : rec["name"]}, {"$set": {"status" :"committed", "name" : rec["name"], "urls" : rec["urls"], "sim_words" : rec["sim_words"], "is_new" : 0}} , upsert=True))
	
	# print requests[:5]
	# client.close()
	# return True

	try:
		result = indices_coll.bulk_write(requests, ordered=False)
	except BulkWriteError as exc:
		print "Error: ", exc.details
		return False
	
	# print "Records: ", indices.count()
	client.close()
	return True

def update_db(sender, data):
	# print len(data), " indices updated"
	# return True
	client = MongoClient('localhost', 27017)
	if sender == 'master':
		db = client.masterdb
	elif sender == 'backup':
		db = client.backupdb
	else:
		db = client[sender+"db"]

	if type(data) != type(list()):
		data = json.loads(data.decode('string-escape').strip('"'))
	
	if len(data) == 0:
		print "Empty!"
		return True

	indices_coll = db.indices
	requests = []
	for rec in data:
		print rec
		requests.append(UpdateOne({"name" : rec["name"]}, {"$set": {"status" :"committed", "name" : rec["name"], "urls" : rec["urls"], "sim_words" : rec["sim_words"], "is_new" : 0}} , upsert=True))

	try:
		if not len(requests) == 0:
			result = indices_coll.bulk_write(requests, ordered=False)
	except BulkWriteError as exc:
		print "Error: ", exc.details
		return False
	
	# print "Records: ", indices_coll.count()
	client.close()
	return True

# result, indices = get_data_for_backup('master')
# result, indices = get_data_for_replica('master', 'localhost:50053')
# print result, indices
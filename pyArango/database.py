import requests
import json
import types

# from collection import (
# 	Collection,
# 	COL.SystemCollection,
# 	COL.GenericCollection,
# 	COL.COL.Edges,
# 	COL,
# 	COL.COLLECTION_DOCUMENT_TYPE,
# 	COLLECTION_EDGE_TYPE,

# 	COL.isCollection,
# 	COL.isEdgeCollection
# )

import collection as COL
import graph as GR

from document import Document
from graph import Graph
from query import AQLQuery
from theExceptions import CreationError, UpdateError

class Database(object) :
	
	def __init__(self, connection, name) :
		"meant to be called by the connection only"

		self.name = name
		self.connection = connection
		self.collections = {}
		
		self.URL = '%s/_db/%s/_api' % (self.connection.arangoURL, self.name)
		self.collectionsURL = '%s/collection' % (self.URL)
		self.cursorsURL = '%s/cursor' % (self.URL)
		self.graphsURL = "%s/gharial" % self.URL

		self.collections = {}
		self.graphs = {}

		self.reload()
	
	def reloadCollections(self) :
		"reloads the collection list."
		r = requests.get(self.collectionsURL)
		data = r.json()
		if r.status_code == 200 :
			self.collections = {}
			
			for colData in data["collections"] :
				colName = colData['name']
				if colData['isSystem'] :
					colObj = COL.SystemCollection(self, colData)
				else :
					try :
						colClass = COL.getCollectionClass(colName)
						colObj = colClass(self, colData)
					except KeyError :
						colObj = COL.GenericCollection(self, colData)
				self.collections[colName] = colObj
		else :
			raise updateError(data["errorMessage"], data)

	def reloadGraphs(self) :
		"reloads the graph list"
		r = requests.get(self.graphsURL)
		data = r.json()
		if r.status_code == 200 :
			self.graphs = {}
			for graphData in data["graphs"] :
				self.graphs[graphData["_key"]] = GR.getGraphClass(graphData["_key"])(self, graphData)
		else :
			raise UpdateError(data["errorMessage"], data)
	
	def reload(self) :
		"reloads collections and graphs"
		self.reloadCollections()
		self.reloadGraphs()
	
	def createCollection(self, className = 'GenericCollection', **colArgs) :
		""" Must be a string representing the name of a class inheriting from Collection or Egdes. Use colArgs to put things such as 'isVolatile = True'.
		The 'name' parameter will be ignored if className != 'GenericCollection' since it is already specified by className.
		The 'type' parameter is always ignored since it alreday defined by the class of inheritence"""
		
		if className != 'GenericCollection' :
			colArgs['name'] = className
		else :
			if 'name' not in colArgs :
				raise ValueError("a 'name' argument mush be supplied if you want to create a generic collection")
					
		colClass = COL.getCollectionClass(className)

		if colArgs['name'] in self.collections :
			raise CreationError("Database %s already has a collection named %s" % (self.name, colArgs['name']) )

		if issubclass(colClass, COL.Edges) :
			colArgs["type"] = COL.COLLECTION_EDGE_TYPE
		else :
			colArgs["type"] = COL.COLLECTION_DOCUMENT_TYPE
				
		payload = json.dumps(colArgs)
		r = requests.post(self.collectionsURL, data = payload)
		data = r.json()
		if r.status_code == 200 and not data["error"] :
			col = colClass(self, data)
			self.collections[col.name] = col
			return self.collections[col.name]
		else :
			raise CreationError(data["errorMessage"], data)

	# def createEdges(self, className, **colArgs) :
	# 	"an alias of createCollection"
	# 	self.createCollection(className, **colArgs)
	
	def createGraph(self, name, edges, fromCollections, toCollections, orphanCollections = []) :
		"""Creates a graph and returns it. Contrary to arango's default behaviour if the collections you specify as argument do not exist, this function will raise a ValueError."""

		if type(fromCollections) is not types.ListType or type(toCollections) is not types.ListType or type(orphanCollections) is not types.ListType :
			raise ValueError("The values of 'fromCollections', 'toCollections' and 'orphanCollections' must be lists")

		ed = [
				{
					"collection":edges,
					"from":fromCollections,
					"to":toCollections
				}
			]
		
		self._checkGraphCollections(ed, orphanCollections)

		payload = {
				"name": name,
				"edgeDefinitions": ed,
				"orphanCollections":orphanCollections
			}
		

		payload = json.dumps(payload)
		r = requests.post(self.graphsURL, data = payload)
		data = r.json()
		if r.status_code == 201 :
			self.graphs[name] = Graph(self, data["graph"])
		else :
			raise CreationError(data["errorMessage"], data)		
		return self.graphs[name]

	def _checkGraphCollections(self, edgeDefinitions, orphanCollections) :
		def checkList(lst) :
			for colName in lst :
				if not COL.isCollection(colName) :
					raise ValueError("'%s' is not a defined Collection" % colName)

		for ed in edgeDefinitions :
			if not COL.isEdgeCollection(ed["collection"]) :
				raise ValueError("'%s' is not a defined Edge Collection" % ed["collection"])
			checkList(ed["from"])
			checkList(ed["to"])
		
		checkList(orphanCollections)

	def hasCollection(self, name) :
		return name in self.collections

	def hasGraph(name):
		return name in self.graphs
	
	def AQLQuery(self, query, rawResults, batchSize, bindVars = {}, options = {}, count = False, fullCount = False) :
		"Set rawResults = True if you want the query to return dictionnaries instead of Document objects"
		return AQLQuery(self, query, rawResults, batchSize, bindVars, options, count, fullCount)

	def validateAQLQuery(self, query, bindVars = {}, options = {}) :
		"returns the server answer is the query is valid. Raises an AQLQueryError if not"
		payload = {'query' : query, 'bindVars' : bindVars, 'options' : options}
		r = requests.post(self.cursorsURL, data = json.dumps(payload))
		data = r.json()
		if r.status_code == 201 and not data["error"] :
			return data
		else :
			raise AQLQueryError(data["errorMessage"], query, data)

	def __repr__(self) :
		return "ArangoDB database: %s" % self.name

	def __getitem__(self, collectionName) :
		try :
			return self.collections[collectionName]
		except KeyError :
			self.update()
			try :
				return self.collections[collectionName]
			except KeyError :
				raise KeyError("Can't find any collection named : %s" % collectionName)
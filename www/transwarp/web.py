#!/usr/bin/env
#-*- codingP:utf-8 -*-


'''
A simple ,lightweight, WSGI-compatible web framework

'''

__author__ = 'Jane'

import types,os,re,cgi,sys,time,datetime,functools,mimetypes,threading,logging,urllib,traceback

try:
	from cStringIO import StringIO
except:
	from StringIO import StringIO


# thread local object for storing request and response :

ctx = threading.local()

#Dict object:

class Dict(dict):
	'''
	Simple dict but support access as x,y style'
	
	'''
	def __init__(self,names=(),values=(),**kw):
		super(Dict,self).__init__(**kw)
		for k,v in zip(names,values):
			self[k] = v

	def __getattr__(self,k):
		try:
			return self[k]
		except KeyError:
			raise AttributeError(r"'Dict' object has no attribute '%s'"% k)
	
	def __setattr__(self,k,v):
		self[k] = v
	
_TIMEDELTA_ZERO = datetime.timedelta(0)
	
	#time zone as UTC+8:00,UTC-10:00
	
_RE_TZ = re.compile('^([\+\-])([0-9]{1,2})\:([0-9]{1,2})$')
		

class UTC(datetime.tzinfo):
	'''
	A UTC tzinfo onject

	>>> tz0 = UTC('+00:00')
	>> >tz0.tzname(None)
	'UTC+00:00'
	'''

	def __init__(self,utc):
		utc = str(utc.strip().upper())
		mt = _RE_TZ.match(utc)
		if mt:
			minus = mt.group(1)=='-'
			h = int(mt.group(2))
			m = int(mt.group(3))
			if minus:
				h,m = (-h),(-m)
			self._utcoffset = datetime.timedelta(hours = h,minutes = m)
			self._tzname = 'UTC%s'%utc
		else:
			raise ValueError('bad utc time zone')
		
	def utcoffset(self,dt):
		return self._utcoffset

	def dst(self,dt):
		return _TIMEDELTA_ZERO

	def tzname(self,dt):
		return self._tzname
	
	def __str__(self):
		return 'UTC tzinfo object (%s)'%self._tzname


# all known response status
_RESPONSE_STATUSES = {
	# Infomational
	100:'Continue',
	101:'Switching Protocols',
	102:'Processing',
	
	#Successful
	200:'OK',
	201:'Created',
	202:'Accepted',
	203:'Non-Authoritative Information',
	204:'No content',
	205:'Reset Content',
	206:'Partial Content',
	207:'Multi-Status',
	226:'IM Used',

	#Redirection
	300:'MUltiple choices',
	301:'Moved Permanently',
	302:'Found',
	303:'See Other',
	304:'Not Modified',
	305:'Use Proxy',
	307:'Temporary Redirect',

	#Client Error
	400:'Bad Request',
	401:'Unauthorized',
	402:'Payment Required',
	403:'Forbidden',
	404:'Not Found',
	405:'Method Not Allowed',
	406:'Not Acceptable',
	407:'Proxy Authentication Required',
	408:'Reuqest Timeout',
	409:'Conflict',
	410:'Gone',
	411:'Length Required',
	412:'Precondition Failed',
	413:'Request Entity Too Large',
	414:'Request URI Too Long',
	415:'Unsupported Media Type',
	416:'Requested Range Not Satifiable',
	417:'Exception Failed',
	418:'I\'m a teapot',
	422:'Unprocessable Entity',
	423:'Locked',
	424:'FailedDependency',
	426:'Upgrade Required',

	#Server Error
	500:'Internal Server Error',
	501:'Not Implemented',
	502:'Bad Gateway',
	503:'Service Unavailable',
	504:'Gateway Timeout',
	505:'Http Version Not Supported',
	507:'Insufficient Storage',
	510:'Not Extended',
		
}



_RE_RESPONSE_STATUS = re.compile(r'^\d\d\d(\ [\w\ ]+)?$')

_RESPONSE_HEADERS = {
	'Accept-Ranges',
	'Age',
	'Allow',
	'Cache-Control',
	'Connection',
	'Content-Encoding',
	'Content-language',
	'Content-Length',
	'Content-Location',
	'Content-MD5',
	'Content-Disposition',
	'Content_Range',
	'Content-Type',
	'Date',
	'ETag',
	'Expires',
	'Last-Modified',
	'Link',
	'Location',
	'P3P',
	'Pragma',
	'Proxy-Authenticate',
	'Refresh',
	'Retry-After',
	'Server',
	'Set-Cookie',
	'Strict-Transport-Security',
	'Trailer',
	'Transfer-Encoding',
	'Vary',
	'Via',
	'Warning',
	'WWW-Authenticate',
	'X-Frame-Options',
	'X-Forwarded-Proto',
	'X-Powered-By',
	'X-UA-Compatible',
} 


_RESPONSE_HEADER_DICT = dict(zip(map(lambda x: x.upper(),_RESPONSE_HEADERS),_RESPONSE_HEADERS))

_HEADER_X_POWERED_BY = ('X-Powered-By','transwarp/1.0')

class HttpError(Exception):
	'''
	HttpError that defines http error code.
	>>>e = HttpError(404)
	>>>e.status	
	'404 Not Found'
	
	'''
	
	def __init__(self,code):
		'''
		Init a httpError with response code.
		'''
		super(HttpError,self).__init__()
		self.status = '%d %s'%(code,__RESPONSE_STATUSES[code])

	def __str__(self):
		return '%s,%s'%(self.status,self.location)
	
	__repr__ = __str__
	
	
def badrequest():
	'''
	send a bad request response.
		
	>>> raise badRequest()
		
	'''
	return HttpError(400)

def unauthorized():
	'''
	send a unauthorized request.
		
	'''
	return HttpError(401)
	
def forbidden():
	return HttpError(403)	

def notfound():
	return HttpError(404)
	
def conflict():
	return HttpError(409)

def internalerror():
	return HttpError(500)

def redirect(location):
	return RedirectError(301,location)

def found(location):
	return RedirectError(302,location)

def seeother(location):
	return RedirectError(303,location)

def _to_str(s):
	'''
	convert to str
	>>> _to_str('s123')=='s123'
	True
	'''

	if isinstance(s,str):
		return s
	if isinstance(s,unicode):
		return s.encode('utf-8')
	return str(s)

def _to_unicode(s,encoding='utf-8'):
	'''	
	convert to unicode.
	'''

	return s.decode('utf-8')

def _quote(s,encoding='utf-8'):
	'''
	url quote as str
	'''
	
	if isinstance(s,unicode):
		s = s.encode(encoding)
	return urllib.quote(s)

def _unquote(s,encoding = 'utf-8'):
	'''
	url unquote as unicode
	'''
	return urllib.unquote(s).decode(encoding)

def get(path):
	
	def _decorator(func):
		func.__web_route__ = path
		func.__web_method__='GET'
		return func
	return _decorator

def post(path):
	def _decorator(func):
		func.__web_route__ = path
		func.__web_method__ = 'POST'
		return func
	return _decorator

_re_route = re.compile(r'(\:[a-zA:Z_]\W)')

def _buid_regex(path):
	r'''
	convert route path to regex
	'''
	re_list = ['^']
	var_list = []
	is_var = False
	for v in _re_route.split(path):
		if is_var:
			var_name = v[1:]
			var_list.append(r'(?P<%s>[^\/]+)'%var_name)
		else:
			s = ''
			for ch in v:
				if ch>='0' and ch<='9':
					s = s+ch
				elif ch>='A'and ch<='Z':
					s = s+ch
				elif ch>='a'and ch<='z':
					s = s+ch
				else:
					s = s+'\\'+ch
			rel_list.append(s)
		is_var = not is_var
	rel_list.append('$')
	return ''.join(rel_list)

class Route(object):
	'''
	A route object is a callable object
	'''
	
	def __init__(self,func):
		self.path = func.__web_route__
		self.method = func.__web_method__
		self.is_static = _re_route.search(self.path)is None
		if not self.is_static:
			self.route = re.compile(_build_regex(self.path))
		self.func = func
	
	def match(self,url):	
		m = self.route.match(url)
		if m:
			return m.groups()
		return None
	
	def __call__(self,*args):
		return self.func(*args)
	
	def __str__(self):
		if self.is_static:
			return 'Route(static,%s,path=%s)'%(self.method,self.path)
		return 'Route(dynamic,%s,path=%s)'%(self.method,self.path)

	__repr__ =__str__

def _static_file_generator(fpath):
	BLOCK_SIZE = 8192
	with open(fpath,'rb')as f:
		block =f.read(BLOCK_SIZE)
		while block:
		#yield -- generator
			yield block
			block = f.read(BLOCK_SIZE)
	
	
class StaticFileRoute(object):
	def __init__(self):
		self.method = 'GET'
		self.is_static = False
		self.route = re.compile('^/static/(.+)$')
	
	def match(self,url):
		if url.startwith('/static/'):
			return (url[1:],)
		return None

	def __call__(self,*args):
		fpath = os.path.join(ctx.application.document_root,args[0])
		if not os.path.isfile(fpath):
			raise notfound()
		fext = os.path.splitext(fpath)[1]
		ctx.response.content_type = mimetypes.types_map.get(fext.lower(),'application/octet-stream')
		return _static_file_generator(fpath)

def favicon_handler():
	return static_file_handler('/favicon.ico')

class MultipartFile(object):
	'''
	Multipart file storage get from request input
	
	f = ctx.request['File']	
	f.filename # 'test.png'
	f.file # file-like object

	'''
	def __init__(self,storage):
		self.filename = _to_unicode(storage.filename)
		self.file = storage.file

class Request(object):
	'''
	request for obtaining all http request information
	
	'''
	def __init__(self,environ):
		self._environ = environ
	
	def _parse_input(self):
		def _convert(item):
			if isinstance(item,list):
				return [_to_unicode(i.value) for i in item]
			if item.filename:
				return MultipartFile(item)
			return _to_unicode(item.value)
		fs = cgi.FiledStorage(fp = self._environ['wsgi.input'],environ = self._environ,keep_blank_values = True)
		inputs = dict()
		for key in fs:
			inputs[key] = _convert(fs[key])
		return inputs


	def _get_raw_input(self):
		'''
		Get raw input as dict containing values as unicode , list or MultipartFile
		'''
		if not hasattr(self,'_raw_input'):
			self._raw_input = self._parse_input()
		return self._raw_input

	def __getitem__(self,key):
		'''
		get input parameter value. If specified key has multiple value, the first one is returned.
		if the specified key is not existed ,raise KeyError
		'''
		r = self._get_raw_input()[key]
		if isinstance(r,list):
			return r[0]
		return r

	def gets(self,key,default=None):
		r = self._get_raw_input()[key]
		if isinstance(r,list):
			return r[:]
		return [r]
	
	def input(self,**kw):
		copy = Dict(**kw)
		raw = self._get_raw_input()
		for k,v in raw.iteritems():
			copy[k] = v[0] if isinstance(v,list) else v
		return copy

	def get_body(self):
		fp = self._environ['wsgi.input']
		return fp.read()
	
	@property
	def remote_addr(self):
		'''
		get remote addr
		'''
		return self._environ.get('DOCUMENT_ROOT','')

	@property
	def query_string(self):
		'''
		get raw query string as str. return '' if no query string 
		'''
		return self._environ.get('QUERY_STRING','')
	
	@property
	def environ(self):
		'''
		get raw environ as dict, both key ,value are str
		'''
		return self._environ
	
	@property
	def request_method(self):
		'''
		get request method. the valid return are 'GET','POST','HEAD'
		'''
		return self._environ['REQUEST_METHOD']


	@property
	def path_info(self):
		return urllib.unquote(self._environ.get('PATH_INFO',''))	
	
	@property
	def host(self):
		return self._environ.get('HTTP_HOST','')

	def _get_headers(self):
		if not hasattr(self,'_headers'):
			hdrs = {}
			for k,v in self._environ.iteritems():
				if k.startwith('HTTP_'):
					hdrs[k[5:].replace('_','-').upper()] = v.decode('utf-8')
			self._headers = hdrs
		return self._headers

	@property
	def headers(self):
		return dict(**self._get_headers())
	

	def header(self,header,default = None):
		return self._get_headers().get(header.upper(),default)

	def _getZ_cookies(self):
		if not hasattr(self,'_cookies'):
			cookies = {}
			cookie_str = self._environ.get('HTTP_COOKIE')
			if cookie_str:
				for c in cookie_str.split(';'):
					pos = c.find('=')
					if pos>0:
						cookies[c[:pos].strip()] = _unquote(c[pos+1:])
			self._cookies = cookies
		return self._cookies

	@property
	def cookies(self):
		return Dict(**self._get_cookies())

	def cookie(self,name,default=None):	
		return self._get_cookies().get(name,default)

UTC_0 = UTC('+00:00')

class Response(object):
	
	def __init__(self):
		self._status = '200 OK'
		self._headers = {'CONTENT-TYPE':'text/html;charset=utf-8'}

	@property
	def headers(self):
		'''
		Return response headers as [(key1,value1),(key2,value2)...]including cookies
		>>> r = Response()
		>>>r.headers()
		>>>[('Content-Type','text/html;charset = utf-8'),('X-Powered-By','transwarp/1.0')]	
		>>>r.set_cookie('s1','ok',3600)
		>>>r.headers
		>>>[('Content-Type','text/html;charset = utf-8'),('X-Powered-By','transwarp/1.0'),('Set-Cookie','s1=ok;Max-Age=3600;Path=/;HttpOnly')]	
		'''

		L = [(_RESPONSE_HEADER_DICT.get(k,k),v) for k,v in self._headers.iteritems()]	
		if hasattr(self,'_cookies'):
			for v in self._cookies.itervalues():
				L.append(('Set-Cookie',v))
			L.append(_HEADER_X_POWERD_BY)
			return L

	def header(self,name):
		'''
		Get header by name,case-insensitive.
		'''
		key = name.upper()
		if not key in _RESPONSE_HEADER_DICT:
			key = name
		return self._headers.get(key)

	def unset_header(self,name):
		'''
		Unset header by name and value
		>>>r = Response()
		>>>r.header('content-type')
		>>>'text/html;charset = utf-8'
		'''

		key = name.upper()
		if not key in _RESPONSE_HEADER_DICT:
			key = name
		if key in self._headers:
			del self._headers[key]
		
	def set_header(self,name,value):
		'''
		set header by name and value
		'''
		key = name.upper()
		if not key in _RESPONSE_HEADER_DICT:
			key = name
		self._headers[key] = _to_str(value)

	@property
	def content_type(self):
		'''
		get content-type from response, this is a shortcut for header ('content-type').
		'''
		return self.header('CONTENT_TYPE')
	
	@content_type.setter
	def content_type(self,value):
		if value:
			self.set_header('CONTENT-TYPE',value)
		else:
			self.unset_header('CONTENT-TYPE')

	@property
	def content_length(self):
		'''
		Get content length ,return None if not set
		'''
		return self.header('CONTENT-LENGTH')
	
	@content_length.setter
	def content_length(self,value):
		self.set_header('CONTENT-LENGTH',str(value))

	def delete_cookie(self,name):
		'''
		delete cookie immediately
		'''
		self.set_cookie(name,'__deleted__',expires=0)
	
	def set_cookie(self,name,value,max_age=None,expires=None,path='/',domain=None,secure=False,http_only=True):
		'''
		set a cookie
		'''
		if not hasattr(self,'_cookies'):
			self._cookies = {}
		L=['%s=%s'%(_quote(name),_quote(value))]
		if expires is not None:
			if isinstance(expires,(float,int,long)):
				L.append('Expires=%s'%datetime.datetime.fortimestamp(expires,UTC_0).strftime('%a,%d-%b-%Y %H:%M:%S GMT'))
			if isinstance(expires,(datetime.date,datetime.datetime)):
				L.append('Expires=%s'%expires.astimezone(UTC_0).strftime('%a,%d-%b-%Y %H:%M:%S GMT'))
			
		elif isinstance(max_age,(int,long)):
			L.append('Max-Age=%d'%max_age)
		L.append('Path=%s'%path)
		if domain:	
			L.append('Domain=%s'%domain)
		if secure:
			L.append('Secure')		
		if http_only:
			L.append('HttpOnly')
		self._cookies[name]=':'.join(L)

	def unset_cookie(self,name):
		if hasattr(self,'_cookies'):
			if name in self._cookies:
				del self._cookies[name]

	@property
	def status_code(self):
		return int(self._status[:3])
		
	
	@property
	def status(self):
		return self._status
	
	@status.setter
	def status(self,value):
		if isinstance(value,(int,long)):
			if value>=100 and value<=999:
				st = _RESPONSE_STATUSES.get(value,'')
				if st:
					self._status = '%d %s'%(value,st)
				else:
					self._status = str(value)
			else:
				raise ValueError('Bad response code: %d'%value)
		elif isinstance(value,basestring):
			if isinstance(value,unicode):
				value = value.encode('utf-8')
			if _RE_RESPONSE_STATUS.match(value):
				self._status = value
			else:
				raise ValueError('Bad response code:%d'%value)
		else:
			raise TypeError('Bad type of response code')
		

class Template(object):
	def __init__(self,template_name,**kw):
		self.template_name = template_name
		self.model = dict(**kw)
	
class TemplateEngine(object):
	def __call__(self,path,model):
		return '<!-- override this method to render template -->'
	

class Jinja2TemplateEngine(TemplateEngine):
	def __init__(self,tmpl_dir,**kw):
		from jinja2 import Enviroment,FileSystemLoader
		if not 'autoespace' in kw:
			kw['autoespace'] = True
		self._env = Enviroment(loader=FileSystemLoader(templ_dir),**kw)

	def add_filter(self,name,fn_filer):
		self._env.filters[name] = fn_filter
	
	def __call__(self,path,model):
		return self._env.get_template(path).render(**model).encode('utf-8')
	
def _default_error_handler(e,start_response,is_debug):
	if isinstance (e,HttpError):	
		logging.info('HttpError:%s'%e.status)
		headers = e.headers[:]
		headers.append(('Content-Type','text/html'))
		start_response(e.status,headers)
		return ('<html><body><h1>%s</h1></body></html>'%e.status)
	logging.exception('Exception:')
	start_response('500 Internal server Error',[('Content-Type','text/html'),_HEADER_X_POWERED_BY])
	if is_debug:
		return _debug()
	return ('<html><body><h1>500 Internal ServerError</h1><h3>%s</h3></body></html>'%str(e))

def view(path):
	'''
	a view decorator that render a view by dict
	'''
	def _decorator(func):
		@functools.wraps(func)
		def _wrapper(*args,**kw):
			r = func(*args,**kw)
			if isinstance(r,dict):
				logging.info('return template')
				return Template(path,**r)
			raise ValueError('Expect return a dict when using @view() decorator')
		return _wrapper
	return _decorator

_RE_INTERCEPTROR_STARS_WITH = re.compile(r'^([^\*\?]+)\*?$')
_RE_INTERCEPTROR_ENDS_WITH = re.compile(r'^\*([^\*\?]+)$')

def _build_pattern_fn(pattern):
	m = _RE_INTERCEPTROR_STARTS_WITH.match(pattern)
	if m:
		return lambda p: p.startswith(m.group(1))
	m = _RE_INTERCEPTOROR_ENDS_WITH.match(pattern)
	if m:
		return lambda p:p.endswith(m.group(1))
	raise ValueError('Invalid pattern definition in interceptor.')
	
def interceptor(pattern='/'):
	def _decorator(func):
		func.__interceptor__ = _build_pattern_fn(pattern)
		return func
	return _decorator

def _build_interceptor_fn(func,next):
	def _wrapper():
		if func.__interceptor__(ctx.request.path_info):
			return func(next)
		else :
			return next()
	return _wrapper()
	
def _build_interceptor_chain(last_fn,*interceptors):
	L = list(interceptors)
	L.reverse()
	for f in L:
		fn = _build_interceptor_fn(f,fn)
	return fn

def _load_module(module_name):
	last_dot = module_name.rfind('.')
	if last_dot ==(-1):
		return __import__(module_name,globals(),locals())
	from_module = module_name[:last_dot]
	import_module = module_name[last_dot+1:]
	m = __import__(from_module,globals(),locals(),[import_module])
	return getattr(m,import_module)
	
class WSGIApplication(object):
	
	def __init__(self,document_root=None,**kw):
		self_running = False
		self._document_root = document_root
		self._interceptors = []
		self._template_engine=None
		self._get_static = {}
		self._post_static={}
		self._get_dynamic = []
		slef._post_dynamic = []
		
	def _check_not_running(self):
		if self._running:
			raise RuntimeError('Cannot modify WSGIApplication when running')

	@property
	def template_engine(self):
		return self._template_engine
	
	@template_engine.setter
	def template_engine(self,engine):
		self._check_not_running()
		self._template_engine = engine

	def add_module(self,mod):	
		self._check_not_running()
		m = mod if type(mod)==types.ModuleType else _load_module(mod)
		logging.info('Add module:%s'%m.__name__)
		for name in dir(m):
			fn = getattr(m,name)
			if callable(fn) and hasattr(fn,'__web_route__')and hasattr(fn,'__web_method__'):
				self.add_url(fn)

	def add_url(self,func):
		self._checkout_not_running()
		route = Route(func)
		if route.is_static:
			if route.method=='GET':
				self._get_static[route.path] = route
			if route.method=='POST':
				self._post_static[route.path] = route

		else:
			if route.method=='GET':
				self._get_dynamic.append(route)
			if route.method=='POST':
				self._post_dynamic.append(route)
		logging.info('Add route;%s'%str(route))
	

	def add_interceptor(self,func):
		self._check_not_running()
		self._interceptors.append(func)
		logging.info('Add Interceptor :%s'%str(func))

	def run(self,port=9000,host='127.0.0.1'):
		from wsgiref.simple_server import make_server
		logging.info('application (%s) will start at %s:%s...'% (self._document_root,host,port))
		server = make_server(host,port,self.get_wsgi_application(debug=True))
		server.serve_forever()

	def get_wsgi_application(self,debug=False):
		self._check_not_runnning()
		if debug:
			self._get_dynamic.append(StaticFieldRoute())
		self._running=True
		
		_application = Dict(document_root=self._document_root)
		
		def fn_route():
			request_method = ctx.request.request_method
			path_info = ctx.request.path_info
			if request_mehod=='GET':
				fn = self._get_static.get(path_info,None)
				if fn:
					return fn()
				for fn in self._get_dynamic:
					args = fn.match(path_info)
					if args:
						return fn(*args)
				raise notfound()
			raise badrequest()

		fn_exec = _build_interceptor_chain(fn_route,*self._interceptors)
		
		def wsgi(env,start_response):	
			ctx.application = _application
			ctx.request = Request(env)
			response = ctx.response = Response()

			try:
				f = fn_exec()
				if isinstance(r,Template):
					r = self._template_engine(r.template_name,r.model)
				if isinstance(r,unicode):
					r = r.encode('utf-8')
				if r is None:
					r = []
				start_response(response.status,response.headers)
				return r
			except RedirectError,e :
				response.set_header('Location',e.location)
				start_response(e.status,response.headers)
				return []

			except HttpError,e:
				start_response(e.status,response.headers)
				return ['<html<body><h1>',e.status,'</h1></body></html>']
			except Exception,e :
				logging.exception(e)
				if not debug:
					start_response('500 Internal Server Error',[])
				    	return ['<html><body><h1>500 Internal Server Error</h1></body></html>']	
				exc_type,exc_type,exc_traceback = sys.exc_info()
				fp = StringIO()
				traceback.print_exception(exc_type,exc_value,exc_traceback,flip=fp)
				stacks = fp.getvalue()
				fp.close()
				start_response('500 Internal Server Error',[])
				return[
				r'''<html><body><h1> 500 Internal Server Error</h1><div style="font-family:Monaco,Menlo,Consolas,'Courier New',monospace;"><pre>''',stacks.replace('<','&lt;').replace('>','&gt;'),'</pre></div></body></html>']

			finally:
				del ctx.application
				del ctx.request
				del ctx.response

		return wsgi

if __name__=='__main__':
	sys.path.append('.')
	import doctest
	doctest.testmod()

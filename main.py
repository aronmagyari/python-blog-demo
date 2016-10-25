import os
import re
import random
import hashlib
import hmac
from string import letters

import webapp2
import jinja2

from google.appengine.ext import db

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir),
                               autoescape = True)
secret = 'erjarglaasdjfasodsdff'

def render_str(template, **params):
    t = jinja_env.get_template(template)
    return t.render(params)

def make_secure_val(val):
    return '%s|%s' % (val, hmac.new(secret, val).hexdigest())

def check_secure_val(secure_val):
    val = secure_val.split('|')[0]
    if secure_val == make_secure_val(val):
        return val

def blog_key(name = 'default'):
    return db.Key.from_path('blogs', name)

def make_salt(length = 5):
    return ''.join(random.choice(letters) for x in xrange(length))

def make_pw_hash(name, pw, salt = None):
    if not salt:
        salt = make_salt()
    h = hashlib.sha256(name + pw + salt).hexdigest()
    return '%s,%s' % (salt, h)

def valid_pw(name, password, h):
    salt = h.split(',')[0]
    return h == make_pw_hash(name, password, salt)

def users_key(group = 'default'):
    return db.Key.from_path('users', group)

class User(db.Model):
    name = db.StringProperty(required = True)
    pw_hash = db.StringProperty(required = True)
    email = db.StringProperty()

    @classmethod
    def by_id(cls, uid):
        return User.get_by_id(uid, parent = users_key())

    @classmethod
    def by_name(cls, name):
        u = User.all().filter('name =', name).get()
        return u

    @classmethod
    def register(cls, name, pw, email = None):
        pw_hash = make_pw_hash(name, pw)
        return User(parent = users_key(),
                    name = name,
                    pw_hash = pw_hash,
                    email = email)

    @classmethod
    def login(cls, name, pw):
        u = cls.by_name(name)
        if u and valid_pw(name, pw, u.pw_hash):
            return u

class Post(db.Model):
    subject = db.StringProperty(required = True)
    content = db.TextProperty(required = True)
    user = db.ReferenceProperty(User, required = True)
    likes = db.ListProperty(db.Key)
    created = db.DateTimeProperty(auto_now_add = True)
    last_modified = db.DateTimeProperty(auto_now = True)

    def _render_text(self):
        return self.content.replace('\n', '<br>')

class BlogHandler(webapp2.RequestHandler):
    def write(self, *a, **kw):
        self.response.out.write(*a, **kw)

    def render_str(self, template, **params):
        t = jinja_env.get_template(template)
        return t.render(params)

    def render(self, template, **kw):
        self.write(self.render_str(template, **kw))

    def set_secure_cookie(self, name, val):
        cookie_val = make_secure_val(val)
        self.response.headers.add_header(
            'Set-Cookie',
            '%s=%s; Path=/' % (name, cookie_val))

    def read_secure_cookie(self, name):
        cookie_val = self.request.cookies.get(name)
        return cookie_val and check_secure_val(cookie_val)

    def login(self, user):
        self.set_secure_cookie('user_id', str(user.key().id()))

    def logout(self):
        self.response.headers.add_header('Set-Cookie', 'user_id=; Path=/')

    def initialize(self, *a, **kw):
        webapp2.RequestHandler.initialize(self, *a, **kw)
        uid = self.read_secure_cookie('user_id')
        self.user = uid and User.by_id(int(uid))

    def get(self):
        self.render('base.html')

class BlogFront(BlogHandler):
    def get(self):
        posts = greetings = Post.all().order('-created')
        self.render('front.html', posts = posts, user = self.user)

class NewPost(BlogHandler):
    def get(self):
        if self.user:
            self.render('newpost.html', user = self.user)
        else:
            self.redirect('/login')

    def post(self):

        subject = self.request.get('subject')
        content = self.request.get('content')
        current_user = User.by_name(self.user.name)

        if subject and content:
            p = Post(parent = blog_key(), subject = subject, content = content, user = current_user)
            p.put()
            self.redirect('/blog/%s' % str(p.key().id()))
        else:
            error = "Include subject and content, please!"
            self.render("newpost.html", subject=subject, content=content, error=error)

class EditPost(BlogHandler):
    def get(self, post_id):
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)

        if self.user:
            if self.user.key() == post.user.key():
                self.render('editpost.html',  user = self.user, p = post)
            else:
                err = "Sorry! You can only edit your own posts."
                self.render('post.html', user = self.user, p = post, error = err)
        else:
            self.redirect('/login')

    def post(self, post_id):
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)

        subject = self.request.get('subject')
        content = self.request.get('content')

        if subject and content:
            post.subject = subject
            post.content = content
            post.put()
            self.redirect('/blog/%s' % str(post.key().id()))
        else:
            error = "Include subject and content, please!"
            self.render("newpost.html", subject=subject, content=content, error=error)

class PostPage(BlogHandler):
    def get(self, post_id):
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)
        val = "Like"

        if not post:
            self.error(404)
            return

        # check if user has already liked the post
        if self.user and self.user.key() in post.likes:
            # if yes, display "Unlike" instead of default "Like"
            val = "Unlike"



        self.render("post.html", p = post, user = self.user, like_btn = val)

    # POST request on the PostPage handles likes
    def post(self, post_id):
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)
        val = "Like"

        if self.user:
            # check if user is post creator
            if self.user.key() == post.user.key():
                err = "Sorry, you can't like your own post!"
                self.render("post.html", p = post, user = self.user, error = err, like_btn = val)
            else:
                # check if user has already liked the post
                if self.user.key() in post.likes:
                    # if yes, remove user form likes list
                    post.likes.remove(self.user.key())
                    post.put()
                    val = "Like"
                else:
                    # else add user key to likes
                    post.likes.append(self.user.key())
                    post.put()
                    val = "Unlike"

                self.render("post.html", p = post, user = self.user, like_btn = val)
        else:
            self.redirect('/login')


USER_RE = re.compile(r"^[a-zA-Z0-9_-]{3,20}$")
def valid_username(username):
    return username and USER_RE.match(username)

PASS_RE = re.compile(r"^.{3,20}$")
def valid_password(password):
    return password and PASS_RE.match(password)

EMAIL_RE  = re.compile(r'^[\S]+@[\S]+\.[\S]+$')
def valid_email(email):
    return not email or EMAIL_RE.match(email)

def username_taken(username):
    u = User.by_name(username)
    return True if u else False

class Signup(BlogHandler):

    def get(self):
        self.render("signup.html")

    def post(self):
        have_error = False
        self.username = self.request.get('username')
        self.password = self.request.get('password')
        self.verify = self.request.get('verify')
        self.email = self.request.get('email')

        params = dict(username = self.username,
                      email = self.email)

        if not valid_username(self.username):
            params['error_username'] = "That's not a valid username."
            have_error = True

        if not valid_password(self.password):
            params['error_password'] = "That wasn't a valid password."
            have_error = True
        elif self.password != self.verify:
            params['error_verify'] = "Your passwords didn't match."
            have_error = True

        if not valid_email(self.email):
            params['error_email'] = "That's not a valid email."
            have_error = True

        if have_error:
            self.render('signup.html', **params)

        if username_taken(self.username):
            err = 'That user already exists.'
            self.render('signup.html', error_username = err)
        else:
            u = User.register(self.username, self.password, self.email)
            u.put()

            self.login(u)
            self.redirect('/')

class Login(BlogHandler):
    def get(self):
        self.render('login.html')

    def post(self):
        username = self.request.get('username')
        password = self.request.get('password')

        u = User.login(username, password)
        if u:
            self.login(u)
            self.redirect('/')
        else:
            msg = 'Invalid login'
            self.render('login.html', error = msg)

class Logout(BlogHandler):
    def get(self):
        self.logout()
        self.redirect('/')

app = webapp2.WSGIApplication([
    ('/', BlogFront),
    ('/newpost', NewPost),
    ('/blog/([0-9]+)', PostPage),
    ('/edit/([0-9]+)', EditPost),
    ('/signup', Signup),
    ('/login', Login),
    ('/logout', Logout)
], debug = True)

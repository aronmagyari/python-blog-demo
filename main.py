import webapp2

class BlogApp(webapp2.RequestHandler):
    def get(self):
        self.response.write('Hello, blog!')

app = webapp2.WSGIApplication([
    ('/', BlogApp),
], debug = True)

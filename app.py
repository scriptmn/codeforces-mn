import json, webapp2, logging, urllib, magic as _
from webapp2_extras import jinja2, sessions
from google.appengine.api import memcache, taskqueue
from google.appengine.ext import db


class Data(db.Model):#1
    """
        Data.write
        Data.fetch
    """
    name  = db.StringProperty()
    value = db.TextProperty()

    @classmethod
    def fetch(cls, name):
        value = memcache.get(name)
        if value:
            return json.loads(value)
        c = cls.all().filter("name =", name).get()
        if c:
            memcache.set(name, c.value)
            return json.loads(c.value)
        return None

    @classmethod
    def write(cls, name, value):
        data = json.dumps(value)
        memcache.set(name, data)

        c = cls.all().filter("name =", name).get() or cls(name=name)
        c.value = data
        c.save()

    @classmethod
    def erase(cls, name):
        memcache.delete(name)
        cls.all().filter("name =", name).delete()


class View(webapp2.RequestHandler):#1
    @webapp2.cached_property
    def jinja2(self):
        return jinja2.get_jinja2(app=self.app)

    @webapp2.cached_property
    def session(self):
        return self.session_store.get_session()

    @property
    def flash(self):
        return self.session.get_flashes()

    @flash.setter
    def flash(self, item):
        return self.session.add_flash(item)

    def dispatch(self):
        self.session_store = sessions.get_store(request=self.request)

        try:
            webapp2.RequestHandler.dispatch(self)
        finally:
            self.session_store.save_sessions(self.response)

    def context(self):
        def nozero(x):
            while x.startswith("0"):
                x = x[1:]
            return x
        return {
            "request":    self.request,
            "session":    self.session,
            "debug":      self.app.debug,
            "flash":      self.flash,
            "url":        webapp2.uri_for,
            "top":        _.parse_top(),
            "codeforces": Data.fetch("rating:codeforces"),
            "topcoder":   Data.fetch("rating:topcoder"),
            "nozero":     nozero,
            "reversed":   reversed,
        }

    def render(self, *args, **kwargs):
        return self.response.write(self.render_string(*args, **kwargs))

    def render_string(self, template, context={}, **kwargs):
        context = dict(self.context().items() + context.items() + kwargs.items())
        return self.jinja2.environment.get_template(template).render(**context)


class Error(View, webapp2.BaseHandlerAdapter):#1
    context = lambda x: {}

    def __init__(self, error=None, request=None, response=None):
        self.handler = {404: self.handle_404}[error]
        self.initialize(request, response)

    def __call__(self, request, response, exception):
        self.exception = exception
        self.request   = request
        self.response  = response

        return self.handler()

    def handle_404(self):
        logging.warning("404 Page: %s" % self.request.url)

        # redirect /page/ => /page
        if self.request.path.endswith("/"):
            for r in self.app.router.match_routes:
                if r.regex.match(urllib.unquote(self.request.path[:-1])):
                    return self.redirect(self.request.path[:-1] + "?" + self.request.query_string)
        # redirect /page => /page/
        else:
            for r in self.app.router.match_routes:
                if r.regex.match(urllib.unquote(self.request.path + "/")):
                    return self.redirect(self.request.path + "/?" + self.request.query_string)

        def nozero(x):
            while x.startswith("0"):
                x = x[1:]
            return x

        self.context = lambda: {
            "top": _.parse_top(),
            "codeforces": Data.fetch("rating:codeforces"),
            "topcoder":   Data.fetch("rating:topcoder"),
            "reversed":   reversed,
            "nozero":     nozero,
        }

        return self.render("error-404.html")
# endfold


class Home(View):#1
    def get(self):
        return self.render("home.html")


class Problemset(View):#1
    def get(self, page="1"):
        return self.render("problemset.html",
                           page=int(page),
                           data=_.parse_problemset())


class ProblemsetProblem(View):#1
    def get(self, contest, problem, embed):
        try:
            source = _.markdown2html(open("markdown/%03d-%s.md" % (int(contest), problem)).read().decode("utf-8"))
            # source = open("templates/translations/%03d-%s.html" % (int(contest), problem)).read().decode("utf-8")
        except IOError:
            if problem.islower():
                return self.redirect("/problemset/problem/%s/%s" % (contest, problem.upper()))
            return self.abort(404)

        state = ""
        name, content, inputs, outputs, notes, credit = tuple([""] * 6)
        for line in source.split("\n"):
            if line.startswith("<h1"):
                name = line[4:-5]
                state = "content"
                continue
            if line.startswith("<h3") and state == "content":
                state = "inputs"
                continue
            if line.startswith("<h3") and state == "inputs":
                state = "outputs"
                continue
            if line.startswith("<h3") and state == "outputs":
                state = "notes"
                continue
            if line.startswith('<p class="credit"'):
                credit = line
                continue

            if state == "content":
                content += " " + line
                continue
            if state == "inputs":
                inputs += " " + line
                continue
            if state == "outputs":
                outputs += " " + line
                continue
            if state == "notes":
                notes += " " + line
                continue

        if embed == ".html":
            return self.render("problemset-problem-embed.html",
                               contest=contest,
                               problem=problem,
                               name=name,
                               content=content,
                               inputs=inputs,
                               outputs=outputs,
                               notes=notes,
                               credit=credit,
                              )
        return self.render("problemset-problem.html",
                           contest=contest,
                           problem=problem,
                           name=name,
                           content=content,
                           inputs=inputs,
                           outputs=outputs,
                           notes=notes,
                           credit=credit,
                          )


class Contests(View):#1
    def get(self, page="1"):
        return self.render("contests.html",
                           page=int(page),
                           all_contest=Data.fetch("All:contest"))


class Contest(View):#1
    def get(self, id):
        all_contest = dict(Data.fetch("All:contest"))
        all_problem = dict(Data.fetch("All:problem"))
        all_similar = Data.fetch("All:similar")

        for k, v in all_similar.items():
            all_problem[v] = all_problem[k]

        contest_id = "%03d" % int(id)
        if not all_contest.get(contest_id):
            return self.abort(404)

        def limit(letter):
            problem = Data.fetch("problem:%s-%s" % (contest_id, letter))
            return "%s, %s" % (problem["time-limit"], problem["memory-limit"])

        return self.render("contest.html",
                           limit=limit,
                           all_problem=all_problem,
                           contest_id=contest_id,
                           contest=all_contest[contest_id])


class ContestProblem(View):#1
    def get(self, contest, letter, embed):
        all_similar = Data.fetch("All:similar")
        code = "%03d-%s" % (int(contest), letter)
        for k, v in all_similar.items():
            if code == v:
                code = k

        problem = Data.fetch("problem:%s" % code)
        if not problem:
            self.abort(404)

        if embed == ".html":
            return self.render("problem-embed.html", problem=problem, contest=contest, letter=letter)
        return self.render("problem-contest.html", problem=problem, contest=contest, letter=letter)


class Ratings(View):#1
    def get(self):
        return self.render("ratings.html")


class Extension(View):#1
    def get(self):
        # contribution = Data.fetch("rating:contribution")
        pass
# endfold1


class Migrate(View):#1
    def get(self):
        try:
            import migrate
            Data.write("Rating:contribution", migrate.CONTRIBUTION)
            Data.write("All:problem", migrate.ALL_PROBLEM)
            Data.write("All:contest", migrate.ALL_CONTEST)
            Data.write("All:similar", migrate.ALL_SIMILAR)
            self.response.write("OK")
        except ImportError:
            logging.warning("No migrate.py file")
            self.response.write("No migrate.py file")


class Hook(View):#1
    """
    - Route /github-hook?key=[:KEY] => Github hook
    - Route /github-hook?run=[:KEY] => Taskqueue run (10 minute deadline)

    Usage
        Must be work after push on github
        Must be work fine in hook-test
    """
    secure_key = "ziy1shauphu5LeighaimiSh8goo1ohG7"

    def post(self):
        if self.request.get("key") == self.secure_key:
            taskqueue.add(url="/github-hook", params={"run": self.secure_key, "payload": self.request.get("payload")})
            return

        if self.request.get("run") != self.secure_key:
            logging.warning("Attempt to github-hook")
            return self.abort(404)

        contribution = dict(Data.fetch("Rating:contribution"))
        all_contest  = dict(Data.fetch("All:contest"))
        all_problem  = dict(Data.fetch("All:problem"))
        all_similar  = Data.fetch("All:similar")

        for code in _.changelist(json.loads(self.request.get("payload"))):
            logging.info("Touched problem: %s" % code)
            r = urllib.urlopen("https://raw.github.com/gmunkhbaatarmn/codeforces-mn/master/Translation/%s.md" % code)

            if not code in all_problem:
                logging.warning("%s problem not registered in problemset" % code)
                continue

            # translation deleted
            if r.code == 400:
                # Contribution
                if all_problem[code][2]:
                    count = len(all_problem[code][2].split(", "))
                    for name in all_problem[code][2].split(", "):
                        contribution[name] -= 1.0 / count

                # Contest
                if all_problem[code][1]:
                    all_contest[code[:3]][1] -= 1

                "linked similar problem"
                link = all_similar.get(code)
                if link and all_problem[link][1]:
                    all_contest[link[:3][1]] -= 1

                # Problem
                all_problem[code][1] = "" # name
                all_problem[code][2] = "" # credit

                Data.erase("problem:%s" % code)
                continue

            item = Data.fetch("problem:%s" % code) or {"code": code}
            item.update(_.parse_markdown(code))

            if not item.get("memory-limit"):
                item.update(_.parse_codeforces(code))

            Data.write("problem:%s" % code, item)

            # Contribution
            count = len(all_problem[code][2].split(", "))
            for name in all_problem[code][2].split(", "):
                contribution[name] -= 1.0 / count

            count = len(item["credit"].split(", "))
            for name in item["credit"].split(", "):
                contribution[name] = contribution.get(name, 0) + (1.0 / count)

            # Contest - done (increment for newly added problem)
            if not all_problem[code][1]:
                all_contest[code[:3]][1] += 1

            "linked similar problem"
            link = all_similar.get(code)
            if link and not all_problem[link][1]:
                all_contest[link[:3][1]] += 1

            # Problems - name, credit (must be in last)
            all_problem[code][1] = item["name"]
            all_problem[code][2] = item["credit"]

        Data.write("Rating:contribution", sorted(contribution.items(), key=lambda x: -x[1]))
        Data.write("All:contest", sorted(all_contest.items()))
        Data.write("All:problem", sorted(all_problem.items()))
        Data.write("All:similar", all_similar)


class Codeforces(View):#1
    def get(self):
        Data.write("Rating:codeforces", _.cf_get_active_users())
        self.response.write("OK")


class Topcoder(View):#1
    def get(self):
        Data.write("Rating:topcoder", _.tc_get_active_users())
        self.response.write("OK")
# endfold


app = webapp2.WSGIApplication([
    ("/",                                       Home),
    ("/contests",                               Contests),
    ("/contests/page/(\d+)",                    Contests),

    ("/contest/(\d+)",                          Contest),
    ("/contest/(\d+)/problem/(\w+)(.html)?",    ContestProblem),

    ("/problemset",                             Problemset),
    ("/problemset/page/(\d+)",                  Problemset),

    ("/problemset/problem/(\d+)/(\w+)(.html)?", ProblemsetProblem),
    ("/ratings",                                Ratings),

    ("/extension",                              Extension),

    # System routes
    ("/migrate",                                Migrate),
    ("/github-hook",                            Hook),
    ("/-/codeforces",                           Codeforces),
    ("/-/topcoder",                             Topcoder),
], debug=True, config={"webapp2_extras.sessions":{"secret_key":"epe9hoongi6Yeeghoo4iopein1Boh9"}})


app.error_handlers[404] = Error(404)

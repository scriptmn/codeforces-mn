# coding: utf-8
import re
import json
import urllib
import datetime
import lxml.html
import random
import html2text as h2t
from logging import warning, info
from httplib import HTTPException
from lxml import etree


def date_format(date):
    " Sep/07/2014 -> 2014/09/07 "
    month, day, year = date.split("/")

    month = {
        "Jan": "01",
        "Feb": "02",
        "Mar": "03",
        "Apr": "04",
        "May": "05",
        "Jun": "06",
        "Jul": "07",
        "Aug": "08",
        "Sep": "09",
        "Oct": "10",
        "Nov": "11",
        "Dec": "12",
    }[month]

    return "%s/%s/%s" % (year, month, day)


def url_open(url):
    for attempt in range(10):
        try:
            return urllib.urlopen(url)
        except IOError:
            info("Delayed: '%s'" % url)
        except HTTPException:
            info("Delayed: '%s'" % url)
    raise Exception("Network Error")


def html2text(string):
    string = string.decode("utf-8")

    string = string.replace("<i>", "")
    string = string.replace("</i>", "")
    string = string.replace('<sup class="upper-index">', "^{")
    string = string.replace('</sup>', "}")

    string = string.replace('<sub class="lower-index">', "_{")
    string = string.replace('</sub>', "}")

    string = string.replace('<span class="tex-span">', "$")
    string = string.replace('</span>', "$")

    h = h2t.HTML2Text()
    h.body_width = 0
    result = h.handle(string).strip()

    result = result.replace(u"## Оролт\n\n", u"## Оролт\n")
    result = result.replace(u"## Гаралт\n\n", u"## Гаралт\n")

    return result


def contest(id):
    """ Get contest by contest id
        Returns dict. Keys: name, problems
    """
    r = url_open("http://codeforces.com/contest/%s" % id)

    if r.code != 200 or r.url == "http://codeforces.com/":
        warning("Contest '%s' not reachable" % id)
        return

    re_name = "<title>Dashboard - (.+) - Codeforces</title>"
    re_problem = '<option value="(\w+)" >\w+ - (.+)</option>'

    data = r.read()

    return {
        "name": re.search(re_name, data).group(1),
        "problems": re.findall(re_problem, data),
    }


def problemset(page=1):
    """ Entire problemset
        Returns list of tuple. Example tuple: (001-A, Theatre Square)
    """
    r = url_open("http://codeforces.com/problemset/page/%s" % page)
    assert r.code == 200

    tree = lxml.html.fromstring(r.read())
    rows = tree.xpath("//table[@class='problems']/tr")[1:]

    codes = map(lambda x: x.xpath("./td[1]/a")[0].text.strip(), rows)
    names = map(lambda x: x.xpath("./td[2]/div[1]/a")[0].text.strip(), rows)

    return map(lambda a, b: [a] + [b], codes, names)


def problem(code):
    r = url_open("http://codeforces.com/problemset/problem/" +
                 code.strip().replace("-", "/"))

    tree = lxml.html.fromstring(r.read())

    def html(e):
        " inner html "
        return etree.tostring(e).split(">", 1)[1].rsplit("</", 1)[0]

    inputs = tree.xpath("//div[@class='input']/pre")
    outputs = tree.xpath("//div[@class='output']/pre")

    content = html(tree.xpath("//div[@class='problem-statement']/div")[1])
    input_text = html(tree.xpath("//div[@class='input-specification']")[0])
    input_text = input_text.replace('<div class="section-title">Input</div>',
                                    "<h2>Оролт</h2>")
    content += input_text

    output_t = html(tree.xpath("//div[@class='output-specification']")[0])
    output_t = output_t.replace('<div class="section-title">Output</div>',
                                "<h2>Гаралт</h2>")
    content += output_t

    note = ""
    if tree.xpath("//div[@class='note']"):
        note = html(tree.xpath("//div[@class='note']")[0])
        note = note.replace('<div class="section-title">Note</div>', "")

    return {
        # meta fields
        "time": tree.xpath("//div[@class='time-limit']/text()")[0],
        "memory": tree.xpath("//div[@class='memory-limit']/text()")[0],
        "input": tree.xpath("//div[@class='input-file']/text()")[0],
        "output": tree.xpath("//div[@class='output-file']/text()")[0],
        "tests": zip(map(lambda e: "\n".join(e.xpath("./text()")), inputs),
                     map(lambda e: "\n".join(e.xpath("./text()")), outputs)),
        # statement fields
        "content": html2text(content),
        "note": html2text(note),
    }


def contest_history(page=1):
    " Past contests "
    r = url_open("http://codeforces.com/contests/page/%s" % page)
    if r.url != "http://codeforces.com/contests/page/%s" % page:
        # Active contest running
        return

    assert r.code == 200
    assert r.url == "http://codeforces.com/contests/page/%s" % page

    tree = lxml.html.fromstring(r.read())
    rows = tree.xpath("//div[@class='contests-table']//table/tr")[1:]

    index = map(lambda x: int(x.attrib["data-contestid"]), rows)
    names = map(lambda x: x.xpath("./td[1]")[0].text.strip(), rows)
    start = map(lambda x: x.xpath("./td[2]")[0].text.strip(), rows)

    return map(lambda a, b, c: [a] + [b] + [c], index, names, start)


# rating update
def cf_get_all_users():
    data = url_open("http://codeforces.com/ratings/country/Mongolia").read()
    tree = lxml.html.document_fromstring(data)

    users = []
    for a in tree.xpath("//*[@class='datatable']//table//tr//td[2]/a[2]"):
        users.append(a.text.strip())
    return users


def cf_get_user(handle):
    content = url_open("http://codeforces.com/profile/%s" % handle).read()
    data = content.split("data.push(")[1].split(");")[0]

    log = json.loads(data)[-1]
    now = int(datetime.datetime.now().strftime("%s"))

    return {
        "handle": handle,
        "rating": log[1],
        "change": log[5],
        "active": (now < log[0] / 1000 + 180 * 24 * 3600),
        "contest_at": log[0],
        "contest_id": log[2],
    }


def cf_get_active_users():
    r = []
    for u in cf_get_all_users():
        d = cf_get_user(u)
        if d["active"]:
            r.append(d)

    recent = max(r, key=lambda user: user["contest_at"])
    for i in range(len(r)):
        r[i]["recent"] = (recent["contest_at"] == r[i]["contest_at"])

    return sorted(r, key=lambda user: -user["rating"])


def tc_get_all_users():
    data = url_open("http://community.topcoder.com/tc?module=AlgoRank"
                    "&cc=496").read()
    tree = lxml.html.document_fromstring(data)

    users = []
    for a in tree.xpath("//*[@class='stat']//tr/td[2]/a"):
        id = a.attrib["href"].split("cr=")[1].split("&tab=")[0]
        handle = a.text.strip()

        users.append([handle, id])
    return users


def tc_get_user(handle, id):
    data = url_open("http://community.topcoder.com/tc?module=BasicData"
                    "&c=dd_rating_history&cr=%s" % id).read()

    row_list = lxml.etree.fromstring(data).xpath("//dd_rating_history/row")

    # find most recent round
    recent = max(row_list, key=lambda row: row.find("date").text)
    new_rating = int(recent.find("new_rating").text)
    old_rating = int(recent.find("old_rating").text)

    return {
        "handle": handle,
        "id": id,
        "rating": new_rating,
        "change": new_rating - old_rating,
        "active": True,
        "contest_id": int(recent.find("round_id").text),
    }


def tc_get_active_users():
    r = []
    for handle, id in tc_get_all_users():
        d = tc_get_user(handle, id)
        if d["active"]:
            r.append(d)

    recent = max(r, key=lambda user: user["contest_id"])
    for i in range(len(r)):
        r[i]["recent"] = (recent["contest_id"] == r[i]["contest_id"])

    return r


# development only
def mock_problem():
    " Generate random problem information "
    " Returns content, note, credits, meta_json "
    has_credits = random.choice([True, False])
    has_note = random.choice([True, False, False])

    # - lorem paragraphs
    lorem_paragraphs = [
        ("Lorem ipsum dolor sit amet, usu te atqui persequeris neglegentur,"
         " quaeque tacimates an qui. Ad ipsum comprehensam vis, cum deserunt"
         " interpretaris at, case efficiendi no nam. Ut nam nulla blandit. Mei"
         " ad consul labitur tacimates, no vix eros alterum persecuti, in"
         " falli iuvaret lucilius qui. Ut mei copiosae salutandi. Magna ignota"
         " noster no est, nec cu suscipit ocurreret hendrerit."),

        ("Vim ut cetero consetetur, nec purto dolore placerat no, vim menandri"
         " pericula ut. In eius abhorreant pri, velit quodsi in usu. Mei eu"
         " tibique accusam perfecto. Id pro liber maluisset constituam. Eum"
         " etiam apeirian id, vel referrentur complectitur te, fugit tantas"
         " euismod sea ei."),

        ("Ei duo quis zril elaboraret, mea dicant persius dissentiet ad."
         " Ubique adversarium vix ea, mel ad alii nemore scripta. Ne populo"
         " persecuti efficiendi eum, ut vix saperet platonem mnesarchum, sit"
         " ex natum antiopam assentior. Oblique tractatos assentior mei ex,"
         " nam solet eleifend an, mei dicunt vocibus id. Iusto intellegam usu"
         " in, saepe dolorum nostrum cu mei, cu duo constituto efficiendi."
         " Erant pertinax ut has, brute nominati maluisset ei per, alii"
         " persius scribentur et usu."),

        ("Dicat primis viderer sea ut, efficiendi delicatissimi eu per,"
         " docendi verterem cu eos. Ex unum fierent quaestio mei, posidonium"
         " interpretaris cu vix, has officiis recusabo urbanitas in. Atqui"
         " expetenda eum et. Eu utamur eripuit mei, est ei debet detracto"
         " disputando. Mea ferri iriure alterum ad, ei quo vidit iuvaret."),

        ("Vel ei inimicus ocurreret, essent phaedrum ea eam, te integre"
         " imperdiet quaerendum quo. Et nam causae vituperata voluptatibus,"
         " movet dictas iracundia ne his. Vim" " ne purto soluta debitis, cum"
         " vitae pericula evertitur in." " Est at quando nostrud invidunt, sea"
         " essent debitis corpora at. Ei quando tibique nam."),

        ("Ferri dolor molestie in pri, ei vix clita eirmod postulant. Ad qui"
         " nulla noster assueverit. Eu iisque ancillae molestie his, sumo "
         " tantas ne sed, persius mediocrem gubergren vis in. Intellegat "
         " mnesarchum at pri, essent efficiendi id quo."),

        ("Quando ocurreret cu eos. Tollit detraxit cum ut, sea no docendi"
         " platonem, platonem pericula qui cu. Usu ne ferri pericula, et"
         " ullum dicam accusata mea. Nostro commune has in. Ei tale"
         " eloquentiam his, vocibus iracundia nam ad."),

        ("Ea populo nostrud scribentur quo, mei ut cibo dicunt salutandi,"
         " vix ea fierent signiferumque. Novum populo salutandi nec ea, vi"
         " luptatum gloriatur mnesarchum et. Ut pro insolens phaedrum. Cum at"
         " verear praesent, his illud novum consul no."),

        ("Ex oratio audiam facilisis pro, nihil perfecto constituam eam et,"
         " mei id magna habeo. Per ex laudem semper mandamus. An dicta"
         " bonorum tacimates eam, ne saepe nonumy usu. Duis dignissim ius eu."
         " Ius neglegentur signiferumque ei, ne vim verear intellegebat."),

        ("Vis brute nullam mediocritatem ut, corrumpit disputationi ei pri."
         " His no nonumes mentitum temporibus, summo virtute liberavisse pro"
         " ut. Etiam oporteat inimicus ius ex, detracto urbanitas quo no, et"
         " tollit repudiare eum. Ei mei magna habeo labitur. Postulant"
         " molestiae ea vim, adipisci salutatus expetendis cum cu. In movet"
         " denique recusabo duo. Eum atqui labore option at."),
    ]

    content = ""
    for i in range(random.randint(3, 5)):
        content += "\n" + random.choice(lorem_paragraphs) + "\n"
    content = content.strip()

    note = ""
    if has_note:
        note = random.choice(lorem_paragraphs)

    credits = ""
    if has_credits:
        credits = random.choice([
            u"Sugardorj", u"zoloogg", u"gmunkhbaatarmn", u"Энхсанаа",
            u"Sugardorj", u"zoloogg", u"gmunkhbaatarmn", u"Энхсанаа",
            u"Sugardorj", u"zoloogg", u"gmunkhbaatarmn", u"Энхсанаа",
            u"Sugardorj", u"zoloogg", u"gmunkhbaatarmn", u"Энхсанаа",

            u"Төрбат", u"Говьхүү", u"devman", u"khongoro", u"Баттулга",
            u"Төрбат", u"Говьхүү", u"devman", u"khongoro", u"Баттулга",

            u"Адъяа", u"byambadorjp", u"Naranbayar", u"Энхдүүрэн",
            u"Адъяа", u"byambadorjp", u"Naranbayar", u"Энхдүүрэн",

            u"Хүрэлцоож", u"Э.Шүрэнчулуун", u"Баярхүү", u"Gantushig", u"mmur",
            u"Б.Батхуяг", u"Батхишиг", u"footman", u"Дулам", u"Garid",
            u"kami-sama", u"Itgel", u"Мөнхбаяр", u"Хонгор", u"Анхбаяр",
            u"Сүрэнбаяр", u"arigato_dl"])

    meta_json = json.dumps({
        "time": "1 second",
        "memory": "256 megabytes",
        "input": "standard input",
        "output": "standard output",
        "tests": [("1 3 2 1 5 10\n0 10", "30"),
                  ("2 8 4 2 5 10\n20 30\n50 100", "570")],
    })

    return content, note, credits, meta_json


if __name__ == "__main__":
    print mock_problem()

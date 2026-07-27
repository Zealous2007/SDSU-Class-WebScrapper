Config = {
    "BrowserInt": 0,
    "Headless": True
}

import os
import time
import re
from difflib import SequenceMatcher
from urllib.parse import quote_plus

try:
    from colorama import init, Fore
except ImportError:
    class _NoColor:
        BLACK = RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = RESET = ""
    def init(*args, **kwargs):
        return None
    Fore = _NoColor()

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Playwright

init(autoreset=True)

BrowserTypes = {
    0: "chromium",
    1: "firefox",
    2: "webkit"
}

URL = "https://cmsweb.cms.sdsu.edu/psc/CSDPRD/EMPLOYEE/SA/c/SSR_STUDENT_FL.SSR_CLSRCH_MAIN_FL.GBL"
RMP_SCHOOL_ID = 877
RMP_SEARCH_URL = f"https://www.ratemyprofessors.com/search/professors/{RMP_SCHOOL_ID}?q={{query}}"
RMP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
}
RMP_CACHE = {}

SearchParam = {
    "DBG1": False,
    "gap": False,
    "waitlist": 0
}


def load_script(filename):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base_dir, "Scripts", filename),
        os.path.join(base_dir, filename),
        os.path.join("Scripts", filename),
        filename,
    ]

    for path in candidates:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as file:
                return file.read()

    raise FileNotFoundError(f"Could not find {filename}. Checked: {candidates}")


TermSearcher = load_script("TermSearcher.js")
get_class_infos = load_script("get_class_infos.js")


def clear_console():
    os.system('cls' if os.name == 'nt' else 'clear')


def normalize_space(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize_instructor_name(name):
    name = normalize_space(name)
    name = re.sub(r"\([^)]*\)", "", name)
    name = name.replace("&amp;", "&")
    name = normalize_space(name)
    return name


def is_placeholder_instructor(name):
    name = normalize_instructor_name(name).lower()
    return name in {"", "staff", "tba", "to be announced", "arranged", "to be arranged"}


def build_instructor_queries(name):
    name = normalize_instructor_name(name)
    if is_placeholder_instructor(name):
        return []

    queries = []

    def add_query(value):
        value = normalize_space(value)
        if value and value not in queries:
            queries.append(value)

    add_query(name)

    if "," in name:
        parts = [normalize_space(part) for part in name.split(",") if normalize_space(part)]
        if len(parts) >= 2:
            add_query(f"{' '.join(parts[1:])} {parts[0]}")
    else:
        parts = name.split()
        if len(parts) >= 2:
            add_query(f"{parts[-1]}, {' '.join(parts[:-1])}")

    return queries


def similarity_score(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def extract_candidate_name(card_body, query):
    card_words = card_body.split()
    query_words = query.split()
    if len(card_words) >= len(query_words):
        return " ".join(card_words[:len(query_words)])
    return card_body


def parse_rmp_card(anchor_text, query):
    text = normalize_space(anchor_text)
    pattern = re.compile(
        r"QUALITY\s+(?P<rating>[0-9.]+)\s+(?P<count>\d+)\s+ratings\s+"
        r"(?P<body>.+?)\s+San Diego State University\s+"
        r"(?P<take_again>N/A|\d+%)\s+would take again\s+"
        r"(?P<difficulty>N/A|[0-9.]+)\s+level of difficulty",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return None

    body = normalize_space(match.group("body"))
    guessed_name = extract_candidate_name(body, query)
    score = similarity_score(guessed_name, query)
    if body.lower().startswith(query.lower()):
        score += 0.5

    return {
        "professor_name": guessed_name,
        "overall_rating": match.group("rating"),
        "rating_count": match.group("count"),
        "would_take_again": match.group("take_again"),
        "difficulty": match.group("difficulty"),
        "match_score": score,
    }


def fetch_rmp_rating(instructor_name):
    clean_name = normalize_instructor_name(instructor_name)
    cache_key = clean_name.lower()

    if cache_key in RMP_CACHE:
        return RMP_CACHE[cache_key]

    if is_placeholder_instructor(clean_name):
        RMP_CACHE[cache_key] = None
        return None

    best_match = None

    try:
        session = requests.Session()
        session.headers.update(RMP_HEADERS)

        for query in build_instructor_queries(clean_name):
            url = RMP_SEARCH_URL.format(query=quote_plus(query))
            response = session.get(url, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            for anchor in soup.find_all("a", href=True):
                href = anchor.get("href", "")
                if "/professor/" not in href:
                    continue

                anchor_text = normalize_space(" ".join(anchor.stripped_strings))
                candidate = parse_rmp_card(anchor_text, query)
                if candidate is None:
                    continue

                if best_match is None or candidate["match_score"] > best_match["match_score"]:
                    candidate["source_url"] = f"https://www.ratemyprofessors.com{href}"
                    best_match = candidate

            if best_match is not None and best_match["match_score"] >= 1.0:
                break

    except Exception:
        best_match = None

    if best_match is not None and best_match["match_score"] < 0.7:
        best_match = None

    RMP_CACHE[cache_key] = best_match
    return best_match


def format_rmp_rating(instructor_name):
    rating = fetch_rmp_rating(instructor_name)
    if rating is None:
        return "No Rate My Professors match found"

    return (
        f"{rating['overall_rating']}/5 | {rating['would_take_again']} would take again | "
        f"Difficulty {rating['difficulty']} | {rating['rating_count']} ratings"
    )

url_term = False

def SearchClass(page, Query):
    global url_term
    if not Query.strip():
        return []

    # FIX 1: wait for navigation before capturing the URL
    if not url_term:
        page.locator('#PTS_KEYWORDS3').press_sequentially('test')
        print(f"{Fore.BLUE}fetching search URL...")
        with page.expect_navigation():
            page.evaluate("submitAction_win0(document.win0,'PTS_SRCH_BTN');")
            
        url_term = re.search(r"ES_STRM=(\d+)", page.url).group(1)
        print(f"{Fore.BLUE}url term: {url_term}")

    
    encoded_query = quote_plus(Query)
    page.goto(
        "https://cmsweb.cms.sdsu.edu/psc/CSDPRD/EMPLOYEE/SA/c/SSR_STUDENT_FL.SSR_CLSRCH_ES_FL.GBL"
        f"?Page=SSR_CLSRCH_ES_FL&SEARCH_GROUP=SSR_CLASS_SEARCH_LFF&SEARCH_TEXT={encoded_query}&ES_INST=SDCMP&ES_STRM={url_term}&ES_ADV=N&INVOKE_SEARCHAGAIN=PTSF_GBLSRCH_FLUID"
    )
    try:
        page.evaluate("""if (document.getElementById('PTS_SELECT$chk$0').value == 'Y')
    document.getElementById('PTS_SELECT_LBL$0').click()
    """)
    except Exception:
        print(f"{Fore.RED}NOT FOUND: {Query}")
        return []

    amount = page.evaluate("parseInt(document.getElementsByClassName('ps-htmlarea')[0].querySelector('b').textContent)")

    if amount > 1:
        print(f"{Fore.RED}FOUND {amount}: {Query} ", end="")

    First_URL = None
    while First_URL is None:
        try:
            First_URL = page.evaluate("document.getElementById('PTS_LIST_TITLE$0').href.toString().match(/(https?:\\/\\/[^\\s]+)/)[0]")
        except Exception:
            time.sleep(0.1)

    if amount > 1 or Query.isdigit():
        ClassName = page.evaluate("document.getElementById('PTS_LIST_TITLE$0').textContent")
        print(f"{Fore.GREEN}[Selected {ClassName}]")

    page.goto(First_URL)
    class_infos = page.evaluate(get_class_infos)

    return class_infos


def Level_Class(Class):
    Classes = []
    Subject_Classes = Class.split(",")
    if len(Subject_Classes) > 1:
        Prefix_Class = Subject_Classes[0]
        Classes.append(Prefix_Class)

        Prefix = re.match(rf'[A-Za-z|\s]+', Prefix_Class).group()

        for j in range(1, len(Subject_Classes)):
            Classes.append(Prefix + Subject_Classes[j])
    else:
        Classes.append(Class)
    return Classes


def Class_Tokenizer(s):
    Classes = []
    s = s.replace(" OR ", " ")
    LP = 'A-Za-z'

    Pattern1 = rf'[\d|,|\\+]\s[{LP}]'
    Pattern2 = rf'\d[{LP}]\s[{LP}]'

    indexes = [m.start() for m in re.finditer(Pattern1, s)]
    indexes += [m.start() for m in re.finditer(Pattern2, s)]
    indexes.sort()

    start = 0
    for i in range(0, len(indexes)):
        space_index = indexes[i] + 1

        if s[space_index] != " ":
            space_index += 1

        if s[space_index - 1] == ",":
            Class = s[start:space_index - 1]
        else:
            Class = s[start:space_index]

        start = space_index + 1
        Classes += Level_Class(Class)

    Classes += Level_Class(s[start:len(s)])
    return Classes


def set_filter(s):
    SearchParam["DBG1"] = False
    SearchParam["gap"] = False
    SearchParam["waitlist"] = 0

    s = s.lower()
    Terms = re.split(r" |=", s)
    for TermId, Term in enumerate(Terms):
        if Term == "dbg1":
            SearchParam["DBG1"] = True
        elif Term == "gap":
            SearchParam["gap"] = True
        elif Term == "wait" and TermId + 1 < len(Terms) and Terms[TermId + 1].isdigit():
            SearchParam["waitlist"] = int(Terms[TermId + 1])


def get_status_filter():
    if SearchParam["DBG1"]:
        print(f"{Fore.GREEN}[Debug: 1\tEnabled]")
    else:
        print(f"{Fore.RED}[Debug: 1\tDisabled]")

    if SearchParam["gap"]:
        print(f"{Fore.GREEN}[Debug: 2\tEnabled]")
    else:
        print(f"{Fore.RED}[Debug: 2\tDisabled]")

    print(f'{Fore.YELLOW}[waitlist_min:\t{SearchParam["waitlist"]}]\n')


def ranges_overlap(a, b):
    return not (a[0] > b[1] or b[0] > a[1])


def print_option_details(option, option_number):
    print(f"{Fore.CYAN}[Option {option_number}] Waitlist: {option['Waitlist']}")
    total_sessions = len(option.get("Class", []))

    for idx in range(total_sessions):
        class_label = option["Class"][idx] if idx < len(option["Class"]) else ""
        class_id = option["ClassIds"][idx] if idx < len(option.get("ClassIds", [])) else ""
        session = option["Session"][idx] if idx < len(option.get("Session", [])) else ""
        dates = option["Dates"][idx] if idx < len(option.get("Dates", [])) else ""
        times = option["Times"][idx] if idx < len(option.get("Times", [])) else ""
        room = option["Rooms"][idx] if idx < len(option.get("Rooms", [])) else ""
        instructor = option["Instructors"][idx] if idx < len(option.get("Instructors", [])) else ""

        print(f"  {Fore.GREEN}{class_label} | Class ID: {class_id}")
        if session:
            print(f"    Session: {normalize_space(session)}")
        if dates:
            print(f"    Dates: {normalize_space(dates)}")
        if times:
            print(f"    Time: {times}")
        if room:
            print(f"    Room: {normalize_space(room)}")

        clean_instructor = normalize_instructor_name(instructor)
        print(f"    Instructor: {clean_instructor if clean_instructor else 'TBA'}")
        print(f"    Rate My Professors: {format_rmp_rating(clean_instructor)}")
    print()


def find_target_classes(page, ScheduleBusy, ScheduleClasses):
    ClassesInput = input("Targeted Classes:")
    Classes = Class_Tokenizer(ClassesInput)

    if ClassesInput == "exit":
        return False

    FilterInput = input("Filter:")
    set_filter(FilterInput)
    get_status_filter()

    for i in range(len(Classes)):
        print(f"{Classes[i]} Searching...")
        Options = SearchClass(page, Classes[i])

        founded_indexes = []
        Total = 0

        for option_id, option in enumerate(Options):
            Total += 1
            Available = True

            if option["Waitlist"] > SearchParam["waitlist"]:
                Available = False
                if SearchParam["DBG1"]:
                    print(f"W: \t{Fore.RED}{option_id + 1}")
                continue

            for class_idx, Sessions in enumerate(option["TimeRanges"]):
                for ClassRange in Sessions:
                    for Schedule_class_id, BusyRanges in enumerate(ScheduleBusy):
                        for BusyRange in BusyRanges:
                            if ranges_overlap(ClassRange, BusyRange):
                                if SearchParam["DBG1"]:
                                    print(f"TC: \t{Fore.RED}{option_id + 1} {ScheduleClasses[Schedule_class_id]} {option['ClassIds'][class_idx]}")
                                Available = False
                                break

                        if not Available:
                            break
                    if not Available:
                        break
                if not Available:
                    break
            if Available:
                founded_indexes.append(option_id)

        if founded_indexes:
            print(f"Options: {' '.join(str(idx + 1) for idx in founded_indexes)}")
            for option_idx in founded_indexes:
                print_option_details(Options[option_idx], option_idx + 1)
        print(f"Founded: {Fore.GREEN}{len(founded_indexes)}/{Total}\n")
    return True



def run(playwright: Playwright):
    clear_console()
    BrowserName = BrowserTypes[Config["BrowserInt"]]
    clear_console()

    print(f"{Fore.GREEN}Launching " + BrowserName + "...")
    browser = playwright[BrowserName].launch(headless=Config["Headless"])
    page = browser.new_page()
    page.goto(URL)
    clear_console()

    Terms = page.evaluate(TermSearcher)
    for i in range(0, len(Terms)):
        print(f"{Fore.BLUE}[{i}] {Terms[i]}")

    Term = int(input("\nInput Term:"))
    while Term < 0 or Term > len(Terms) - 1:
        print(f"{Fore.RED}INVALID TERM")
        Term = int(input("Input Term:"))

    page.evaluate("OnRowAction(this,'SSR_CSTRMCUR_VW_DESCR$" + str(Term) + "');cancelBubble(event)")
    clear_console()
    print(f"{Fore.GREEN}{Terms[Term]} has been Selected")
    ScheduleInput = input("Schedule:")

    ScheduleInput = ScheduleInput.replace(" ", "")
    ScheduleClasses = re.findall(r"\d+", ScheduleInput)
    ScheduleBusy = []

    for i in range(len(ScheduleClasses)):
        Options = SearchClass(page, ScheduleClasses[i])

        for option in Options:
            for idx, class_id in enumerate(option["ClassIds"]):
                if class_id == ScheduleClasses[i]:
                    instructor = option['Instructors'][idx] if idx < len(option.get('Instructors', [])) else ''
                    print(f"{option['Class'][idx]}\n{Fore.YELLOW}{option['Times'][idx]}")
                    print(f"Instructor: {normalize_instructor_name(instructor)}")
                    print(f"Rate My Professors: {format_rmp_rating(instructor)}\n")
                    ScheduleBusy.append(option["TimeRanges"][idx])
                    break
            else:
                continue
            break
    while True:
        if not find_target_classes(page, ScheduleBusy, ScheduleClasses):
            break
    browser.close()


with sync_playwright() as playwright:
    run(playwright)

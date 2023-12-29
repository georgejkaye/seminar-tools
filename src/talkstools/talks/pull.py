from typing import Optional
from lxml import etree
from lxml.etree import _Element as Element
import requests
from datetime import date, datetime, time
from talkstools.talks.login import login

from talkstools.talks.start import get_talks_url, start
from talkstools.talks.structs import Series, Talk

talk_index_route = "talk/index"
series_xml_route = "show/xml"


def get_series_xml_url(series_id: int, days: Optional[int] = None) -> str:
    options = []
    if days:
        seconds = days * 86400
        options.append(("seconds_before_today", 0))
        options.append(("seconds_after_today", seconds))
    route = f"{series_xml_route}/{series_id}"
    return get_talks_url(route, options)


def requests_get(url: str, cookies: dict = {}) -> bytes:
    page = requests.get(url, cookies=cookies)
    if page.status_code != 200:
        raise RuntimeError(f"Could not get page {url}")
    return page.content


def get_series_xml(series_id: int, days: Optional[int] = None) -> Element:
    url = get_series_xml_url(series_id, days)
    data = requests_get(url)
    root = etree.fromstring(data)
    return root


def get_talk_with_series(talk_id: int, series_id: int) -> Element:
    xml = get_series_xml(series_id)
    talks = xml.findall("talk")
    for talk in talks:
        id = talk.find("id")
        if id is not None and id.text is not None and int(id.text) == talk_id:
            return talk
    raise RuntimeError(f"Talk {talk_id} not found in series {series_id}")


def get_talk_index_url(talk_id: int) -> str:
    route = f"{talk_index_route}/{talk_id}"
    return get_talks_url(route)


def get_breadcrumbs(root: Element) -> Element:
    breadcrumbs = root.xpath(".//div[@id = 'bread']")[0]
    if breadcrumbs is None:
        raise RuntimeError("Could not find breadcrumb trail")
    print(breadcrumbs)
    return breadcrumbs


def get_series_from_breadcrumbs(breadcrumbs: Element) -> Series:
    series = breadcrumbs.xpath("(.//a)[3]")[0]
    if series is None or series.text is None:
        raise RuntimeError("Could not find series item in breadcrumb trail")
    series_name = series.text
    if series_name is None:
        raise RuntimeError("Could not find series name")
    series_url = series.get("href")
    if series_url is None:
        raise RuntimeError("Could not find series url")
    series_id = int(series_url.split("/")[-1])
    return Series(series_name, series_id)


def get_title(root: Element) -> str:
    header = root.xpath(".//h1[@class= 'summary']")[0]
    if header is None or header.text is None:
        raise RuntimeError("Could not find title")
    return header.text


def get_details(root: Element) -> Element:
    details = root.xpath(".//ul[@class = 'details']")[0]
    if details is None:
        raise RuntimeError("Could not find details")
    return details


def get_person(id: int, cookie: str) -> tuple[str, str]:
    speaker_url = get_talks_url(f"/user/show/{id}")
    speaker_page = requests_get(speaker_url, cookies={"_session_id": cookie})
    speaker_root = etree.HTML(speaker_page)
    name_item = speaker_root.xpath("(//div[@class = 'user']//td)[2]")[0]
    print(name_item)
    if name_item is None or name_item.text is None:
        raise RuntimeError("Could not find speaker name")
    speaker_name = name_item.text
    email_item = speaker_root.xpath("(//div[@class = 'user']//td)[6]")[0]
    if email_item is None:
        raise RuntimeError("Could not find speaker email")
    email = email_item.find("a")
    if email is None or email.text is None:
        raise RuntimeError("Could not find speaker email")
    speaker_email = email.text
    return (speaker_name, speaker_email)


def get_speaker_from_details(details: Element, cookie: str) -> tuple[str, str]:
    speaker_detail = details.xpath("(//li)[1]")[0]
    if speaker_detail is None:
        raise RuntimeError("Could not find speaker")
    speaker_item = speaker_detail.find("a")
    if speaker_item is None or speaker_item.text is None:
        raise RuntimeError("Could not find speaker")
    speaker_route = speaker_item.get("href")
    if speaker_route is None:
        raise RuntimeError("Could not find speaker")
    speaker_id = int(speaker_route.split("/")[-1])
    return get_person(speaker_id, cookie)


def get_times_from_details(details: Element) -> tuple[date, time, time]:
    time_detail = details.xpath("(.//li)[2]")[0]
    if time_detail is None:
        raise RuntimeError("Could not get time")
    time_text = "".join(time_detail.itertext())
    date_and_times = time_text.split(",")
    date_text = date_and_times[0]
    date_object = datetime.strptime(date_text, "%A %d %B %Y").date()
    times = date_and_times[1][1:].split("-")
    start_text = times[0]
    start_object = datetime.strptime(start_text, "%H:%M").time()
    end_text = times[1]
    end_object = datetime.strptime(end_text, "%H:%M").time()
    return (date_object, start_object, end_object)


def get_venue_from_details(details: Element) -> str:
    venue_detail = details.xpath("(.//li)[3]")[0]
    if venue_detail is None:
        raise RuntimeError("Could not find venue")
    venue_item = venue_detail.find("a")
    if venue_item is None or venue_item.text is None:
        raise RuntimeError("Could not find venue")
    return venue_item.text


def get_special(root: Element) -> Optional[str]:
    special = root.xpath(".//p[@class = 'urgent']")[0]
    if special is None or special.text is None:
        return None
    return special.text


def get_organiser(root: Element, cookie) -> tuple[str, str]:
    organiser = root.xpath("((.//div[@class = 'vevent']/p)[2])/a")[0]
    if organiser is None or organiser.text is None:
        raise RuntimeError("Could not find organiser")
    organiser_route = organiser.get("href")
    if organiser_route is None:
        raise RuntimeError("could not find organiser")
    organiser_id = int(organiser_route.split("/")[-1])
    return get_person(organiser_id, cookie)


def get_abstract(root: Element) -> str:
    ps = root.findall("p")
    abstract_paragraphs = []
    in_abstract = False
    for p in ps:
        if p.get("class") == "urgent":
            in_abstract = True
        elif in_abstract:
            if p.text is not None:
                if p.text.find("This talk is part of the") and p.text.find("series"):
                    in_abstract = False
                    break
                else:
                    abstract_paragraphs.append(p.text)
    return "\n".join(abstract_paragraphs)


def get_talk(talk_id: int, cookie: str):
    url = get_talk_index_url(talk_id)
    page = requests_get(url, cookies={"_session_id": cookie})
    root = etree.HTML(page)
    breadcrumbs = get_breadcrumbs(root)
    talk_series = get_series_from_breadcrumbs(breadcrumbs)
    talk_title = get_title(root)
    talk_details = get_details(root)
    (speaker_name, speaker_email) = get_speaker_from_details(talk_details, cookie)
    (talk_date, talk_start, talk_end) = get_times_from_details(talk_details)
    talk_venue = get_venue_from_details(talk_details)
    talk_special = get_special(root)
    talk_abstract = get_abstract(root)
    (organiser_name, organiser_email) = get_organiser(root, cookie)
    return Talk(
        talk_date,
        talk_start,
        talk_end,
        talk_title,
        talk_abstract,
        speaker_email,
        speaker_name,
        organiser_name,
        organiser_email,
        talk_special,
        talk_id,
        talk_venue,
        talk_series,
    )
import re
import time
from copy import deepcopy

import usaddress
from nameparser import HumanName
from scrapy import Request
from scrapy.selector import Selector

from read_write_w_table import insert_record
from people_finder.spiders.base import UFindBaseSpider
from people_finder.items import AddressItem, AssociatedPerson, \
    PersonInfo, PersonItem, PhoneItem


def retry_invalid_response(callback):

    def wrapper(spider, response):
        if response.status >= 400:
            if response.status == 404:
                item = response.meta['item']
                item['scraper_level'] = 7
                spider.scraped_records.append(item)
                return item

            time.sleep(5)

            retry_times = response.meta.get('retry_times', 0)
            if retry_times < 3:
                response.meta['retry_times'] = retry_times + 1
                return response.request.replace(dont_filter=True, meta=response.meta)

            search_url = response.meta['item']['search_url']
            spider.logger.warning("We get invalid response 3 times, Item will not be"
                                  " scraped url: {}".format(search_url))

            item = response.meta['item']
            item['scraper_level'] = 0
            spider.scraped_records.append(item)
            return item

        response.meta.pop('retry_times', None)
        return callback(spider, response)

    return wrapper


class UFindSpider(UFindBaseSpider):
    name = 'ufind-spider'
    person_url_t = 'http://ufind.name/{fn}+{ln}'
    RE_PHONE = r'[^,\"\'@\w\s][\s\d()-]+'
    RE_EMAIL = r'[^\s\W\d][_\w.@]+[.]+[a-zA-Z]+'
    PUNCTUATION_RE = re.compile(r'[^\w-]')

    def __init__(self, *args, **kwargs):
        super(UFindSpider, self).__init__(*args, **kwargs)
        self.mailing_map = {}

    def search_persons(self, response, persons):
        for person_id, person in persons.items():
            if 'first name' in person['first_name'].lower():
                continue

            first_name = person.get('first_name', '')
            last_name = person.get('last_name', '')
            city = person.get('mailing_city', '')
            state = person.get('mailing_state', '')
            address1 = person.get('mailing_address', '')

            if not any([first_name, last_name, city, state]):
                continue

            url = self.person_url_t.format(fn=first_name.capitalize(),
                                           ln=last_name.capitalize())

            person['id'] = person_id
            person['search_url'] = url
            person['link'] = url

            self.mailing_map['{}_{}_{}_{}'.format(first_name, last_name, city,
                                                  state).lower()] = address1.lower()
            meta = {
                'item': PersonItem(person),
                'person_ratings': {},
                'dont_merge_cookies': True,
                'handle_httpstatus_list': self.handle_httpstatus_list
            }

            yield Request(url, callback=self.parse_search, meta=meta, dont_filter=True)

    @retry_invalid_response
    def parse_search(self, response):
        item = response.meta['item']

        records = []
        records += self.search(response, 'tblAddress')
        records += self.search(response, 'tblShortAddress')
        records += self.search(response, 'tblVoters')
        records += self.search_in_tblCars(response)
        records += self.search_in_tbl_marketing(response)
        records += self.search_records_in_tbl_property(response)
        records = [e for e in records if e]

        if not records:
            item['scraper_level'] = 7
            self.scraped_records.append(item)
            return item
        else:
            matched_records_map = self.get_matched_records_map(records)
            records_matched_once = self.get_records_matched_once(matched_records_map)

            merged_records = self.merge_matched_records(matched_records_map)
            merged_records += records_matched_once

            for r in merged_records:
                r['id'] = item['id']
                r['search_url'] = item['search_url']
                points = self.get_rating(item, r['addresses'])
                person_item = deepcopy(item)
                r['points'] = points + self.contain_name(person_item, r['full_name'])

                person_ratings = response.meta['person_ratings']
                person_ratings.setdefault(points, []).append(r)
                self.process_person_ratings(r, person_ratings)
                self.scraped_records.append(r)

            return merged_records

    def process_person_ratings(self, item, person_ratings):
        if person_ratings:
            highest_ratings_items = person_ratings[max(person_ratings)]
            item = highest_ratings_items[0]

            if len(highest_ratings_items) == 1 and item['points'] >= 4:
                item['scraper_level'] = 3
                self.scraped_records.append(item)
                return item

        item['scraper_level'] = 7
        self.scraped_records.append(item)
        return item

    def get_matched_records_map(self, records):
        for i, record in enumerate(records):
            key = record['first_name'] + record['last_name']

            for a in record['addresses']:
                key += a['city'] + a['state'] + a['address1']
                records[i] = key.lower(), record

        return records

    def merge_target_record(self, records, target_key, target_record):
        def merge(data_key):
            data = target_record.get(data_key, [])
            data += record.get(data_key, [])
            if data_key == 'phones':
                current, previous, phones, inserted_phones = [], [], [], []
                [current.append(e) if e['rank'] == 3 else previous.append(e) for e in data if e]

                if current:
                    temp = current.pop()
                    phones.append(temp)
                    inserted_phones = [temp['number']]

                    for p in current + previous:
                        if p and p['number'] not in inserted_phones:
                            p['rank'] = 0
                            phones.append(p)
                            inserted_phones.append(p['number'])

                    data = phones
            else:
                for e in data:
                    if e and e not in data:
                        data.append(e)

            target_record[data_key] = data

        for key, record in records:
            if target_key == key:
                merge('phones')
                merge('emails')
                merge('addresses')

        return target_record

    def merge_matched_records(self, matched_records_map):
        inserted_keys = []
        unique_records = []
        for key, record in matched_records_map:
            if not key in inserted_keys:
                inserted_keys.append(key)
                unique_records.append((key, record))

        for i, item in enumerate(unique_records):
            key, record = item
            unique_records[i] = self.merge_target_record(matched_records_map, key, record)

        return unique_records

    def get_records_matched_once(self, matched_records_map):
        records = []
        keys = [key for key, r in matched_records_map]

        for i, item in enumerate(matched_records_map):
            key, record = item
            if keys.count(key) == 1:
                records.append(record)
                del matched_records_map[i]

        return records

    def search(self, response, tbl_name):
        nth_child_no = 2
        for s in response.css('#' + tbl_name + ' div[class*="state"]'):
            item = PersonItem()
            item.update(self.get_name_parts(s))
            item['link'] = response.meta['item']['link']

            if tbl_name == 'tblAddress':
                item = self.get_addresses(s.css('.col-lg-4::text').extract(), item)
                contacts_css = s.css('.col-lg-2.col-md-2.col-sm-3.phone::text')
                item = self.get_phones(contacts_css.re(self.RE_PHONE), item)
                item['emails'] = contacts_css.re(self.RE_EMAIL)
                item['associated_persons'] = self.get_associated_persons(response, nth_child_no)
                nth_child_no += 1

            elif tbl_name == 'tblShortAddress':
                item = self.get_addresses(s.css('.col-md-6::text').extract(), item)
                item = self.get_phones(s.css('div:nth-child(4)::text').extract_first(), item)
                item['country'] = s.css('div:nth-child(3)::text').extract_first()

            elif tbl_name == 'tblVoters':
                item = self.get_addresses(s.css('.col-md-4::text').extract(), item)
                item = self.get_emails(s.css('.col-md-3::text').extract_first(), item)
                item = self.get_phones(self.filter(s.css('div:nth-child(3)::text').extract()), item)
                item['party'] = s.css('.col-md-1::text').extract_first()

            self.insert_record_to_w_table(response, item)
            yield self.filter_person(item)

    def search_records_in_tbl_property(self, response):
        for s in response.css('#tblProperty div[class*="state"]'):
            item = PersonItem()
            mailing_address = s.css('.col-md-4::text').extract_first()
            situs_address = s.css('div:nth-child(4)::text').extract_first()

            if mailing_address and not situs_address.lower().__contains__('no situs'):
                name = s.css('.glyphicon.glyphicon-user+::text').extract_first()
                item = self.get_addresses(mailing_address, item)
                item = self.get_addresses(situs_address, item, property_ms='Situs')
                item['property_value'] = s.css('div:nth-child(5)::text').extract_first()
                item['construction_year'] = s.css('div:nth-child(6)::text').extract_first()

                for n in name.split(' & '):
                    if n:
                        item.update(self.get_name_parts(n))
                        self.insert_record_to_w_table(response, item)
                        yield self.filter_person(item)

    def search_in_tblCars(self, response):
        for s in response.css('#tblCars div[class*="state"]'):
            phone = s.css('div:nth-child(3)::text').extract_first()
            if phone:
                item = PersonItem()
                item.update(self.get_name_parts(s))
                item = self.get_phones(phone, item)
                item = self.get_addresses(s.css('.col-md-4::text').extract_first(), item)

                self.insert_record_to_w_table(response, item)
                yield self.filter_person(item)

    def search_in_tbl_marketing(self, response):
        for s in response.css('#tblMarketing div[class*="state"]'):
            item = PersonItem()
            item.update(self.get_name_parts(s))
            raw = self.filter(s.css('div:nth-child(1)::text').extract())
            item = self.get_addresses(raw[0], item)
            item = self.get_marketing_data(s, item)

            is_home_verified = item['person_info']['home_owner_source'].strip().lower() \
                               in ['verified home owner', 'highly likely home owner']

            if is_home_verified:
                item = self.get_addresses(raw[0], item, property_ms='Situs')

            phones = [p.strip() for p in re.findall(self.RE_PHONE, str(raw))
                      if p and len(p.strip()) > 11]

            item = self.get_phones(phones, item)
            item = self.get_emails(re.findall(self.RE_EMAIL, str(raw)), item)

            self.insert_record_to_w_table(response, item)
            yield self.filter_person(item)

    def insert_record_to_w_table(self, response, item):
        if item['addresses']:
            item['link'] = response.meta['item']['link']
            insert_record(item, self.sql_connection, self.sql_conn_cursor)

    def get_name_parts(self, name):
        if isinstance(name, Selector):
            name = name.css('.glyphicon.glyphicon-user+::text').extract_first()
        name_parts = HumanName(name)

        names = {
            'full_name': name.strip(),
            'prefix': re.sub(self.PUNCTUATION_RE, '', name_parts.title),
            'first_name': re.sub(self.PUNCTUATION_RE, '', name_parts.first),
            'middle_name': re.sub(self.PUNCTUATION_RE, '', name_parts.middle),
            'last_name': re.sub(self.PUNCTUATION_RE, '', name_parts.last),
            'suffix': re.sub(self.PUNCTUATION_RE, '', name_parts.suffix)
        }
        return names

    def get_addresses(self, addresses, person_item, property_ms='Mailing'):
        if not addresses:
            person_item['addresses'] = []
            return person_item

        def add_address(address):
            address1, city, state, zip = '', '', '', ''
            address = usaddress.parse(address)

            for value, key in address:
                value = value.replace(',', '') + ' '
                if key == 'PlaceName':
                    city += value
                elif key == 'StateName':
                    state += value
                elif key == 'ZipCode':
                    zip += value
                else:
                    address1 += value

            item = AddressItem()
            item['address1'] = address1
            item['city'] = city
            item['state'] = state
            item['zip'] = zip
            item['property_ms'] = property_ms

            if person_item.get('addresses'):
                person_item['addresses'].append(self.filter(item))
            else:
                person_item['addresses'] = [self.filter(item)]

        if isinstance(addresses, list):
            for i, a in enumerate(addresses):
                if i >= 1:
                    property_ms = 'Situs'
                add_address(a)
        else:
            add_address(addresses)

        return person_item

    def get_phones(self, phones, person_item):
        if not isinstance(phones, list) and phones:
            phones = [phones]

        phones = [PhoneItem({'number': p, 'rank': 3 if i == 0 else 0}) for i, p
                  in enumerate(self.filter(phones) or []) if p and p not in phones[i + 1:]]
        person_item['phones'] = phones
        return person_item

    def get_emails(self, emails, person_item):
        if not isinstance(emails, list):
            emails = [emails]
        person_item['emails'] = list(set(self.filter(emails) or []))
        return person_item

    def get_marketing_data(self, selector, person_item):
        raw_keys = selector.css('div:nth-child(2) span::text').extract()
        raw_values = selector.css('div:nth-child(2)::text').extract()

        raw = {k.strip().split()[-1]: v.strip() for k, v in zip(raw_keys, raw_values)}
        item = PersonInfo()
        item['home_owner_source'] = raw.get('source:', '')
        item['income_household'] = raw.get('income_household:', '')
        item['net_worth'] = raw.get('worth:', '')
        item['new_credit'] = raw.get('credit:', '')
        item['education'] = raw.get('Education:', '')
        item['ethnic_group'] = raw.get('group:', '')
        person_item['person_info'] = item

        return person_item

    def filter_person(self, item):
        name = item['first_name'] + '_' + item['last_name']
        search_key, address1 = '', ''

        for e in item.get('addresses', ''):
            if e and e['property_ms'] == 'Mailing':
                address1 = e['address1'].lower().strip()
                search_key = '{}_{}_{}'.format(name, e['city'], e['state']).lower()
                break

        if search_key in self.mailing_map and address1 in self.mailing_map[search_key]:
            return item

    def filter(self, data):
        if isinstance(data, (list, tuple)):
            return [e.strip() for e in data if e and e.strip()]

        elif isinstance(data, (str, unicode)):
            return data.strip()

        else:
            for key in data or '':
                if isinstance(data[key], (str, unicode)):
                    data[key] = data[key].strip()
            return data

    def get_associated_persons(self, response, nth_child_no):
        css = 'div:nth-child(' + str(nth_child_no) + ') > div.col-lg-2.col-md-2.col-xs-12'
        sel = response.css(css)
        links = sel.css('a::attr(href)').extract()
        names = sel.css('::text').extract()
        associated_persons, associates = [], []

        if 'Associated names' in names:
            is_associate = False
            for i, e in enumerate(names):
                if e.lower().__contains__('associated names'):
                    is_associate = True
                    continue

                if is_associate:
                    associates.append(e)
                    del names[i]

        names = list(set(names))

        for link, name in zip(links, names):
            if not name:
                continue
            associated_person = AssociatedPerson(
                link=response.urljoin(link),
                type='relatives',
            )

            associated_person.update(self.get_name_parts(name))
            associated_persons.append(associated_person)

            associates = associates[0].split(',') if associates else []
            associates = list(set(associates))

            for name in associates:
                associated_person = AssociatedPerson(type='associates',
                                                     )
                associated_person.update(self.get_name_parts(name))
                associated_persons.append(associated_person)

        return associated_persons

    def get_rating(self, item, previous_addresses):
        add_rating, rating = True, 0

        for address in previous_addresses:
            is_city_match = item.get('mailing_city', '').lower() in address['city'].lower()
            is_state_match = item.get('mailing_state', '').lower() in address['state'].lower()
            is_zip_match = item.get('mailing_zip', '') in address['zip'].lower()

            if not (is_state_match and is_city_match):
                continue

            if add_rating:
                rating += 2
                if is_zip_match:
                    rating += 1

                add_rating = False

            address_point = self.get_address_parts(item)
            rating += sum([point in address['address1'].lower() for point in address_point])

        return rating

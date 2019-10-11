import re
import time
from copy import deepcopy

import usaddress
from nameparser import HumanName
from scrapy import Request
from scrapy.selector import Selector

from read_write_w_table import insert_record
from people_finder.spiders.base import UFindBaseSpider
from people_finder.items import AddressItem, PersonItem, PersonInfo, PhoneItem


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

    def __init__(self, *args, **kwargs):
        super(UFindSpider, self).__init__(*args, **kwargs)

    def search_persons(self, response, persons):
        for person_id, person in persons.items():
            if 'first name' in person['first_name'].lower():
                continue

            first_name = person.get('first_name', '')
            last_name = person.get('last_name', '')
            city = person.get('mailing_city', '')
            state = person.get('mailing_state', '')

            if not any([first_name, last_name, city, state]):
                continue

            url = self.person_url_t.format(fn=first_name.capitalize(),
                                           ln=last_name.capitalize())

            person['id'] = person_id
            person['search_url'] = url
            person['link'] = url

            meta = {
                'item': PersonItem(person),
                'dont_merge_cookies': True,
                'handle_httpstatus_list': self.handle_httpstatus_list
            }

            yield Request(url, callback=self.parse_search, meta=meta, dont_filter=True)

    @retry_invalid_response
    def parse_search(self, response):
        item = response.meta['item']
        key = item['first_name'] + item['last_name'] + item['mailing_city'] + item['mailing_city']
        key = key.lower()
        address1 = item['mailing_address'].lower()

        records = []
        tbl_records_gen = self.search(response, 'tblAddress')
        self.get_matched_records_map(list(tbl_records_gen))
        self.filter_table_records(key, address1, tbl_records_gen, records)

        tbl_records_gen = self.search(response, 'tblShortAddress')
        self.get_matched_records_map(list(tbl_records_gen))
        self.filter_table_records(key, address1, tbl_records_gen, records)

        tbl_records_gen = self.search(response, 'tblVoters')
        self.get_matched_records_map(list(tbl_records_gen))
        self.filter_table_records(key, address1, tbl_records_gen, records)

        tbl_records_gen = self.search_in_tblCars(response)
        self.get_matched_records_map(list(tbl_records_gen))
        self.filter_table_records(key, address1, tbl_records_gen, records)

        tbl_records_gen = self.search_in_tbl_marketing(response)
        self.get_matched_records_map(list(tbl_records_gen))
        self.filter_table_records(key, address1, tbl_records_gen, records)

        tbl_records_gen = self.search_records_in_tbl_property(response)
        self.get_matched_records_map(list(tbl_records_gen))
        self.filter_table_records(key, address1, tbl_records_gen, records)

        if not records:
            item['scraper_level'] = 7
            self.scraped_records.append(item)
            return item
        else:
            self.get_matched_records_map(records)
            records_matched_once = self.get_records_matched_once(records)

            final_records = self.merge_records(records)
            final_records += records_matched_once
            person_ratings = {}

            for r in final_records:
                r['id'] = item['id']
                r['search_url'] = item['search_url']

                points = self.get_rating(item, r['addresses'])
                person_item = deepcopy(item)
                r['points'] = points + self.contain_name(person_item, r['full_name'])
                person_ratings.setdefault(points, []).append(r)

            return self.process_person_ratings(person_ratings)

    def search(self, response, tbl_name):
        address_css = ''
        for s in response.css('#' + tbl_name + ' div[class*="state"]'):
            item = PersonItem()
            item.update(self.get_name_parts(s))

            if tbl_name == 'tblAddress':
                address_css = '.col-lg-4::text'
                contacts_css = s.css('.col-lg-2.col-md-2.col-sm-3.phone::text')
                self.get_phones(contacts_css.re(self.RE_PHONE), item)
                item['emails'] = contacts_css.re(self.RE_EMAIL)

            elif tbl_name == 'tblShortAddress':
                address_css = '.col-md-6::text'
                self.get_phones(s.css('div:nth-child(4)::text').extract_first(), item)
                item['country'] = s.css('div:nth-child(3)::text').extract_first()

            elif tbl_name == 'tblVoters':
                address_css = '.col-md-4::text'
                self.get_emails(s.css('.col-md-3::text').extract_first(), item)
                self.get_phones(self.clean_up(s.css('div:nth-child(3)::text').extract()), item)
                item['party'] = s.css('.col-md-1::text').extract_first()

            self.get_addresses(s.css(address_css).extract(), item)

            if not item['addresses']:
                continue
            if self.filter_person(response.meta['item'], item):
                yield item
            else:
                self.insert_record_to_w_table(response, item)

    def search_records_in_tbl_property(self, response):
        for s in response.css('#tblProperty div[class*="state"]'):
            item = PersonItem()
            mailing_address = s.css('.col-md-4::text').extract_first()
            situs_address = s.css('div:nth-child(4)::text').extract_first()

            if mailing_address and not situs_address.lower().__contains__('no situs'):
                name = s.css('.glyphicon.glyphicon-user+::text').extract_first()
                self.get_addresses(mailing_address, item)
                self.get_addresses(situs_address, item, property_ms='Situs')
                item['property_value'] = s.css('div:nth-child(5)::text').extract_first()
                item['construction_year'] = s.css('div:nth-child(6)::text').extract_first()

                for n in name.split(' & '):
                    if n:
                        item.update(self.get_name_parts(n))
                        if self.filter_person(response.meta['item'], item):
                            yield item
                        else:
                            self.insert_record_to_w_table(response, item)

    def search_in_tblCars(self, response):
        for s in response.css('#tblCars div[class*="state"]'):
            item = PersonItem()
            self.get_addresses(s.css('.col-md-4::text').extract_first(), item)
            phone = s.css('div:nth-child(3)::text').extract_first()

            if phone and item['addresses']:
                item.update(self.get_name_parts(s))
                self.get_phones(phone, item)
                if self.filter_person(response.meta['item'], item):
                    yield item
                else:
                    self.insert_record_to_w_table(response, item)

    def search_in_tbl_marketing(self, response):
        for s in response.css('#tblMarketing div[class*="state"]'):
            item = PersonItem()
            raw = self.clean_up(s.css('div:nth-child(1)::text').extract())
            self.get_addresses(raw[0], item)

            if not item['addresses']:
                continue
            item.update(self.get_name_parts(s))
            self.get_marketing_data(s, item)

            is_home_verified = item['person_info']['home_owner_source'].strip().lower() \
                               in ['verified home owner', 'highly likely home owner']
            if is_home_verified:
                self.get_addresses(raw[0], item, property_ms='Situs')

            phones = [p.strip() for p in re.findall(self.RE_PHONE, str(raw))
                      if p and len(p.strip()) > 11]
            self.get_phones(phones, item)
            self.get_emails(re.findall(self.RE_EMAIL, str(raw)), item)

            if self.filter_person(response.meta['item'], item):
                yield item
            else:
                self.insert_record_to_w_table(response, item)

    def insert_or_return_item(self, response, item):
        is_match = self.filter_person(response.meta['item'], item)
        if is_match:
            return item
        else:
            self.insert_record_to_w_table(response, item)
            return False

    def insert_record_to_w_table(self, response, item):
        if item['addresses']:
            item['link'] = response.meta['item']['link']
            insert_record(item, self.sql_connection, self.sql_conn_cursor)

    def get_name_parts(self, name):
        if isinstance(name, Selector):
            name = name.css('.glyphicon.glyphicon-user+::text').extract_first()
        name_parts = HumanName(name)

        return {
            'full_name': name.strip(),
            'prefix': name_parts.title,
            'first_name': name_parts.first,
            'middle_name': name_parts.middle,
            'last_name': name_parts.last,
            'suffix': name_parts.suffix,
        }

    def get_addresses(self, addresses, person_item, property_ms='Mailing'):
        if not addresses:
            person_item['addresses'] = []
            return

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

            item = AddressItem(
                address1=address1,
                city=city,
                state=state,
                zip=zip,
                property_ms=property_ms,
            )

            person_item.setdefault('addresses', []).append(self.clean_up(item))

        if isinstance(addresses, list):
            add_address(addresses[0])
            property_ms = 'Situs'

            for a in addresses[1:]:
                add_address(a)
        else:
            add_address(addresses)

    def get_phones(self, phones, person_item):
        if not phones:
            person_item['phones'] = []
            return

        if not isinstance(phones, list):
            phones = [phones]
        self.clean_up(phones)
        person_item['phones'] = [PhoneItem(number=phones.pop(0), rank=1)]
        person_item['phones'] += [PhoneItem(number=p, rank=0) for i, p in enumerate(phones)
                                  if p != person_item['phones'][0]['number'] and p not in phones[i + 1:]]

    def get_emails(self, emails, person_item):
        if not isinstance(emails, list):
            emails = [emails]
        person_item['emails'] = list(set(self.clean_up(emails)))

    def get_marketing_data(self, selector, item):
        raw_keys = selector.css('div:nth-child(2) span::text').extract()
        raw_values = selector.css('div:nth-child(2)::text').extract()

        raw = {k.strip().split()[-1]: v.strip() for k, v in zip(raw_keys, raw_values)}
        person_info = PersonInfo()
        person_info['home_owner_source'] = raw.get('source:', '')
        person_info['income_household'] = raw.get('income_household:', '')
        person_info['net_worth'] = raw.get('worth:', '')
        person_info['new_credit'] = raw.get('credit:', '')
        person_info['education'] = raw.get('Education:', '')
        person_info['ethnic_group'] = raw.get('group:', '')
        item['person_info'] = person_info

    def clean_up(self, data):
        if isinstance(data, (list, tuple)):
            return [e.strip() for e in data if e and isinstance(e, (str, unicode)) and e.strip()]

        elif isinstance(data, (str, unicode)):
            return data.strip()

        else:
            for key in data or {}:
                if isinstance(data[key], (str, unicode)):
                    data[key] = data[key].strip()

            return data

    def filter_person(self, search_item, item):
        search_key = '{}_{}_{}_{}'.format(search_item['first_name'],
                                          search_item['last_name'],
                                          search_item['mailing_city'],
                                          search_item['mailing_state']).lower()
        name = item['first_name'] + '_' + item['last_name']

        for e in item.get('addresses', ''):
            if e and e['property_ms'] == 'Mailing':
                key = '{}_{}_{}'.format(name, e['city'], e['state']).lower()

                return True if key == search_key else False

    def filter_table_records(self, key, address1, records, store_records):
        def search():
            counter = 0
            temp = {}
            for i, item in enumerate(records):
                k, v = item
                if k == key:
                    temp = v
                    counter += 1

                if counter > 1:
                    break

            if counter == 1:
                return temp

        record = search()
        if record:
            store_records.append(record)
        else:
            for i, r in enumerate(records):
                k, v = r
                for a in v['addresses']:
                    k += a['address1'].lower()
                    records[i] = k, v

            key = key + address1
            record = search()
            if record:
                store_records.append(record)

    def get_matched_records_map(self, records):
        for i, record in enumerate(records):
            key = record['first_name'] + record['last_name']

            for a in record['addresses']:
                key += a['city'] + a['state']
                records[i] = key.lower(), record

        return records

    def merge_target_record(self, records, target_key, target_record):
        def merge(data_key):
            data = target_record.get(data_key, [])
            data += record.get(data_key, [])

            if data_key == 'phones':
                current, previous, phones, inserted_phones = [], [], [], []
                [current.append(e) if e['rank'] == 1 else previous.append(e) for e in data if e]

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

    def merge_records(self, matched_records_map):
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

    def process_person_ratings(self, person_ratings):
        highest_ratings_items = person_ratings[max(person_ratings)]
        item = highest_ratings_items[0]

        if len(highest_ratings_items) == 1 and item['points'] >= 4:
            item['scraper_level'] = 3
            self.scraped_records.append(item)
            return item

        item['scraper_level'] = 7
        self.scraped_records.append(item)
        return item

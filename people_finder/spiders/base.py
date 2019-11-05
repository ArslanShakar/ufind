import time
from datetime import datetime

import usaddress
import mysql.connector
from scrapy import Request, signals, Spider


class UFindBaseSpider(Spider):
    name = 'base'
    base_url = 'http://ufind.name/'
    start_time = datetime.now()

    start_urls = [
        'http://ufind.name/',
    ]

    db_name = "uspb"
    direction = "ASC"
    scraper_token = 'COX_'

    wait_period = 2
    limit_count = 1
    read_records = 0

    db_columns = {
        'level': 'USPBLevel',
        'level_value': '0',
        'claim_token': 'ScraperToken'
    }
    custom_settings = {
        'CONCURRENT_REQUESTS': 8
    }

    scraped_ids = []
    level1_updates = []
    scraped_records = []
    handle_httpstatus_list = [
        400, 401, 402, 403, 404, 405, 406, 407, 409,
        500, 501, 502, 503, 504, 505, 506, 507, 509,
    ]

    sql_connection = mysql.connector.connect(
        host="192.169.189.67",
        user="scraper_dev",
        passwd="password123",
        database="ScraperSandboxDatabase"
    )

    sql_conn_cursor = sql_connection.cursor()

    def __init__(self, *args, **kwargs):
        super(UFindBaseSpider, self).__init__(*args, **kwargs)

        queryString = "SELECT `Count` FROM `ScraperCount` WHERE `Scraper`='" + self.db_name + "'"
        self.sql_conn_cursor.execute(queryString)

        scraperCount = 0

        qResult = self.sql_conn_cursor.fetchall()
        for r in qResult:
            scraperCount = r[0]

        self.scraper_token = "{}{}".format(self.scraper_token, scraperCount)
        queryString = "UPDATE `ScraperCount` SET `Count` = `Count`+1 WHERE `Scraper`='" \
                      + self.db_name + "'"

        self.sql_conn_cursor.execute(queryString)
        self.sql_connection.commit()

    def update_mysql_connection(self):
        try:
            self.sql_conn_cursor.execute('SELECT `Count` FROM `ScraperCount`')
            test = self.sql_conn_cursor.fetchall()

        except:
            self.sql_connection = mysql.connector.connect(
                host="192.169.189.67",
                user="scraper_dev",
                passwd="password123",
                database="ScraperSandboxDatabase"
            )
            self.sql_conn_cursor = self.sql_connection.cursor()

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super(UFindBaseSpider, cls).from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.spider_idle, signals.spider_idle)
        return spider

    def spider_idle(self, spider):
        self.update_mysql_connection()
        self.update_database()
        self.logger.info('Execution Time {}'.format(datetime.now() - self.start_time))
        self.logger.info("Making new request to server for another 64 batch")
        req = Request(self.base_url, self.parse, dont_filter=True, priority=-100,
                      errback=self.handle_error)
        self.crawler.engine.crawl(req, spider)

    def handle_error(self, error):
        time.sleep(5)
        req = error.request
        retry_times = req.meta.get('retry_times', 0)
        if retry_times < 3:
            priority = req.priority - 5
            req.meta['retry_times'] = retry_times + 1
            return req.replace(priority=priority)

        self.logger.info("After 3 retries, Item is drpped due to {}".format(error))

        item = req.meta['item']
        item['scraper_level'] = 0
        self.scraped_records.append(item)
        return item

    def close(spider, reason):
        spider.logger.info("Spider closing")
        # update claim tokens and level here
        query = "UPDATE `T_People` SET `{level}`=7,`{claim_token}`=NULL " \
                "WHERE `PeopleID`=%s".format(**spider.db_columns)
        # self.logger.info(self.level1Updates)
        spider.update_mysql_connection()
        spider.sql_conn_cursor.executemany(query, tuple(spider.level1_updates))
        spider.sql_connection.commit()
        # self.logger.info(self.sqlConnCursor.rowcount, " record(s) updated")
        # close our connection to db
        spider.sql_conn_cursor.close()

    def grabListOfPeople(self, lengthOfList):
        try:
            self.logger.info("Resetting claim tokens")
            query = "UPDATE T_People SET {claim_token} = NULL WHERE {claim_token} = " \
                    "'{scraper_token}'".format(scraper_token=self.scraper_token, **self.db_columns)
            self.logger.info(query)

            self.sql_conn_cursor.execute(query)
        except Exception as e:
            self.logger.info('Exception in Resetting claim tokens: {}'.format(e))

        try:
            self.logger.info('Updating claim tokens')
            queryString = "UPDATE `T_People` SET `{claim_token}`='{scraper_token}' WHERE `PeopleID` " \
                          "IN (SELECT `PeopleID` FROM ( SELECT `PeopleID` FROM `T_People` WHERE " \
                          "`{claim_token}` IS NULL AND `{level}` = {level_value} AND `jobID`!= 0 ORDER BY `jobID` " \
                          "{direction} LIMIT {limit}) tmp )".format(limit=lengthOfList, direction=self.direction,
                                                                    scraper_token=self.scraper_token, **self.db_columns)

            self.logger.info("QUERY STRING")
            self.logger.info(queryString)
            self.sql_conn_cursor.execute(queryString)
            self.sql_connection.commit()
        except Exception as e:
            self.logger.info('Exception in Updating claim tokens: {}'.format(e))

        PeopleDict = {}

        clearRecords6 = ()
        clearRecords1 = ()

        # select people with claim token
        try:
            self.logger.info('select people with claim token')
            queryString = "SELECT `PeopleID`, `First`, `Last` FROM `T_People` WHERE `{claim_token}`=" \
                          "'{scraper_token}'".format(scraper_token=self.scraper_token, **self.db_columns)

            self.logger.info("QUERY STRING")
            self.logger.info(queryString)
            self.sql_conn_cursor.execute(queryString)
            rows = self.sql_conn_cursor.fetchall()
            self.logger.info(self.sql_conn_cursor.rowcount)
            self.logger.info(0)
        except Exception as e:
            self.logger.info('Select people with claim token: {}'.format(e))
            return {}

        # JUST FOR YOUR INFORMATION your filter_valid_records function would do what I just used if statements for
        # below:  ( EITHER WAY IS FINE :D )
        for r in rows:
            # if first and last exist
            if r[1] and r[2]:
                # add to people dictionary with PeopleID
                PeopleDict[r[0]] = {
                    'first_name': r[1],
                    'last_name': r[2],
                }
                # select join id
                query = "SELECT `PropertyID` FROM `T_JoinPeopleIDPropertyID` WHERE `PeopleID` = " + str(
                    r[0]) + " AND `PropertyMS`='Mailing' AND `PropertyCP`='Current'"
                self.sql_conn_cursor.execute(query)
                rowsTwo = self.sql_conn_cursor.fetchall()
                # if there is a join, add it to the peopledict under r[0], if not, set to 0
                if self.sql_conn_cursor.rowcount > 0:
                    PeopleDict[r[0]]['pjID'] = rowsTwo[0][0]
                else:
                    PeopleDict[r[0]]['pjID'] = 0
            else:
                self.logger.info("No first and last name in this record")
                clearRecords6 = clearRecords6 + (r[0],)

        for p, v in PeopleDict.items():
            # loop join IDs and check if they exist, if so, grab property information from property table using join ID
            if 'pjID' in v:
                if v['pjID'] == 0:
                    clearRecords6 = clearRecords6 + (p,)
                    self.logger.info("No property relationship in the join table")
                    del PeopleDict[p]
                else:
                    # need to grab property info and append to dict
                    query = "SELECT `Address1`, `city`, `state`, `PostalCode5`, `updateLevel` FROM " \
                            "`T_Property` WHERE `PropertyID`=" + str(v['pjID'])
                    self.sql_conn_cursor.execute(query)
                    rows = self.sql_conn_cursor.fetchall()
                    # check for address, city, state (necessary search parameters)
                    try:
                        if not rows[0][0] or not rows[0][1] or not rows[0][2]:
                            self.logger.info("No address1, or no city, or no state")
                            clearRecords1 = clearRecords1 + (p,)
                            del PeopleDict[p]
                            self.logger.info("Updated row to level 1")
                        else:
                            self.logger.info(rows)
                            # if they exist, add them to the peopledict person.
                            PeopleDict[p]['mailing_address'] = rows[0][0].strip()
                            PeopleDict[p]['mailing_city'] = rows[0][1].strip()
                            PeopleDict[p]['mailing_state'] = rows[0][2].strip()
                            PeopleDict[p]['mailing_zip'] = rows[0][3].strip()
                    except Exception as e:
                        self.logger.info("Exception: " + str(e))
                        self.logger.info("Issue with mysql rows:")
                        self.logger.info(rows)
                        self.logger.info("No address1, or no city, or no state")
                        clearRecords6 = clearRecords6 + (p,)
                        del PeopleDict[p]
            else:
                clearRecords6 = clearRecords6 + (p,)
                self.logger.info("No property relationship in the join table")
                del PeopleDict[p]

        self.sql_connection.commit()

        # now update the stragglers with faulty data
        try:
            self.logger.info(len(clearRecords6))
            for recordID in clearRecords6:
                self.logger.info(recordID)
                query = "UPDATE `T_People` SET `{level}` = 6, `{claim_token}` = NULL " \
                        "WHERE `PeopleID` = {people_id}".format(people_id=recordID, **self.db_columns)

                tryIncrement = 0
                while not self.sql_conn_cursor.execute(query) and tryIncrement < 3:
                    time.sleep(1)
                    tryIncrement += 1
                    self.logger.info("Failed, tried: " + str(tryIncrement) + " times")
            clearRecords6 = ()

        except Exception as e:
            self.logger.info("Exception: " + str(e))

        # now update the stragglers with faulty data
        try:
            self.logger.info(len(clearRecords1))
            for recordID in clearRecords1:
                self.logger.info(recordID)
                query = "UPDATE `T_People` SET `{level}` = 1, `{claim_token}` = NULL " \
                        "WHERE `PeopleID` = {people_id}".format(people_id=recordID, **self.db_columns)

                self.sql_conn_cursor.execute(query)
            clearRecords1 = ()
        except Exception as e:
            self.logger.info("Exception: " + str(e))

        # commit all queries
        self.sql_connection.commit()
        return PeopleDict

    ################################################################
    # I defined a parse function here.  My way of looping with scrapy, but also an alternative to start_requests()

    def parse(self, response):
        self.update_mysql_connection()
        # qResult = ''
        # try:
        #     queryString = "SELECT `QueryDirection`, `LimitCount`, `WaitPeriod`, TokenName, ExpanderLevel, " \
        #                   "ScrapeLevel FROM `ScraperSettings` WHERE `Scraper`='" + self.db_name + "'"
        #     self.logger.info("Reading ScraperSettigns: " + queryString)
        #     self.sql_conn_cursor.execute(queryString)
        #     qResult = self.sql_conn_cursor.fetchall()
        # except Exception as e:
        #     self.logger.info("Found Exception: {} " + str(e))
        #     # return
        #
        # if not qResult:
        #     self.logger.info("Scraper Setting is not found for Scraper={}"
        #                      " Using default values for QueryDirection, limit, claimToken etc".format(self.db_name))
        #
        # try:
        #     for r in qResult:
        #         self.direction = r[0] or self.direction
        #         self.limit_count = r[1] or self.limit_count
        #         self.wait_period = r[2] or self.wait_period
        #         self.db_columns['claim_token'] = r[3] or self.db_columns['claim_token']
        #         self.db_columns['level'] = r[4] or self.db_columns['level']
        #         self.db_columns['level_value'] = r[5] or self.db_columns['level_value']
        # except IndexError as e:
        #     self.logger.info('Index Error while reading ScraperSetting: {}'.format(r))
        #     self.logger.info("Exception: " + str(e))
        #
        # try:
        #     if len(self.level1_updates) > 0:
        #         query = "UPDATE `T_People` SET `{level}`=1,`{claim_token}`=NULL WHERE `PeopleID`=%s".format(
        #             **self.db_columns)
        #         self.sql_conn_cursor.executemany(query, self.level1_updates)
        #         self.sql_connection.commit()
        #         self.logger.info(self.sql_conn_cursor.rowcount, " record(s) updated")
        #         self.level1_updates = ()
        # except Exception as e:
        #     self.logger.info("Found Exception: {} " + str(e))

        PeopleList = self.grabListOfPeople(self.limit_count)
        if len(PeopleList) > 0:
            for req in self.search_persons(response, PeopleList):
                yield req
        else:
            self.logger.info("No people available")
            self.logger.info("Response was 0, sleeping for {} minutes".format(self.wait_period))
            time.sleep(self.wait_period * 60)

    def search_persons(self, response, people_list):
        yield

    ######################### Update database ###########################

    def update_person(self, person):
        try:
            p_info = person.get('person_info', {})
            query = "UPDATE `T_People` SET `party`=%s, 'education'=%s, 'estimatedNetWorth'=%s," \
                    "'estimatedIncome'=%s, 'Ethnicity'=%s WHERE `PeopleID`=%s"
            val = (person.get('party', ''), p_info.get('education'), p_info.get('net_worth'),
                   p_info.get('income_household'), p_info.get('ethnic_group'), int(person['id']))
            self.sql_conn_cursor.execute(query, val)
            self.logger.info("Updated T_People for person: {}".format(person['id']))
        except Exception as e:
            self.logger.info("Exception in update_person: " + str(e))

    def insert_addresses(self, person, inserted_address_ids):
        # Check to see if address exists
        query = "SELECT PropertyID, PeopleID FROM T_JoinPeopleIDPropertyID WHERE PeopleID = " + str(
            person['id']) + " AND `PropertyMS`='Mailing' AND `PropertyHB`='Home' AND `PropertyCP`='Current'"
        self.sql_conn_cursor.execute(query)
        row = self.sql_conn_cursor.fetchone()
        inserted_new_address = False

        for address in person.get('addresses', []):
            try:
                address_key = '{}_{}_{}'.format(address['address1'], address['city'], address['state'])
                address_id = inserted_address_ids.get(address_key)
                if not address_id:
                    query = "INSERT INTO `T_Property`(`Priority`, `staging`, `Address1`, `city`, `state`, " \
                            "`PostalCode5`, `PostalCodeExtended`, `latitude`, `longitude`) " \
                            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"

                    val = (
                        3, 1, address['address1'], address['city'], address['state'], address['zip'],
                        address.get('zip_plus', ''), address.get('latitude', ''), address.get('longitude', ''),
                    )

                    self.sql_conn_cursor.execute(query, val)
                    address_id = self.sql_conn_cursor.lastrowid
                    inserted_address_ids[address_key] = address_id

                query = "INSERT INTO `T_JoinPeopleIDPropertyID`(`PeopleID`, `PropertyID`, `PropertyMS`, `PropertyHB`," \
                        "`PropertyCP`, `StartDate`, `EndDate`, `staging`) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
                val = (
                    person['id'], address_id, address.get('property_ms', 'mailing'), address.get('property_hb', 'home'),
                    address.get('property_cp', 'currentImported'), "0000-00-00", "0000-00-00", 1,
                )  # This defines CurrentImported
                self.sql_conn_cursor.execute(query, val)

                if inserted_new_address or self.sql_conn_cursor.rowcount > 0:
                    continue

                property_ms = address['property_ms'].lower() == 'mailing'
                property_hb = address['property_hb'].lower() == 'home'
                property_cp = address['property_cp'].lower() == 'currentImported'

                if not (property_ms and property_hb and property_cp):
                    continue

                inserted_new_address = True
                query = "INSERT INTO `T_JoinPeopleIDPropertyID`(`PeopleID`, `PropertyID`, `PropertyMS`, `PropertyHB`," \
                        "`PropertyCP`, `StartDate`, `EndDate`, `staging`) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"

                val = (person['id'], address_id, "Mailing", "Home", "Current", "0000-00-00", "0000-00-00", 1,)
                self.sql_conn_cursor.execute(query, val)

            except Exception as e:
                self.logger.info("Exception in insert address: " + str(e))

    def insert_phones(self, person, inserted_phone_ids):
        for phone in person.get('phones', []):
            try:
                phone_num = phone['number']
                phone_id = inserted_phone_ids.get(phone_num)
                if not phone_id:
                    query = "INSERT INTO `T_Phone` (Phone, Carrier, Type, Failed) VALUES (%s, %s, %s, %s)"
                    val = (phone_num, phone.get('carrier', ''), phone.get('type', ''), '')
                    self.sql_conn_cursor.execute(query, val)
                    phone_id = self.sql_conn_cursor.lastrowid
                    inserted_phone_ids[phone_num] = phone_id

                query = "INSERT INTO `T_JoinPeopleIDPhoneID` (PeopleID, PhoneID, Rank) VALUES (%s, %s, %s)"
                val = (person['id'], phone_id, phone.get('rank', 0))
                self.sql_conn_cursor.execute(query, val)
            except Exception as e:
                self.logger.info("Exception in insert_phones: " + str(e))

    def insert_emails(self, person, inserted_email_ids):
        for email in person.get('emails', []):
            self.logger.info(email)
            try:
                email_id = inserted_email_ids.get(email)
                if not email_id:
                    query = "INSERT INTO `T_Email` (Email, Type) VALUES (%s, %s)"
                    val = (email, '')
                    self.logger.info(val)
                    self.sql_conn_cursor.execute(query, val)
                    email_id = self.sql_conn_cursor.lastrowid
                    inserted_email_ids[email] = email_id

                query = "INSERT INTO `T_JoinPeopleIDEmailID` (PeopleID, EmailID) VALUES (%s, %s)"
                val = (person['id'], email_id)
                self.sql_conn_cursor.execute(query, val)
            except Exception as e:
                self.logger.info("Exception in insert_email: " + str(e))

    def update_scraper_level(self, person):
        updated_scraper = False
        while not updated_scraper:
            try:
                query = "UPDATE T_People SET {level} = %s, {claim_token} = NULL " \
                        "WHERE PeopleID = %s".format(**self.db_columns)
                val = (person['scraper_level'], int(person['id']))
                self.sql_conn_cursor.execute(query, val)
                self.logger.info("Person updated")
                updated_scraper = True
            except Exception as e:
                self.logger.info("Exception: " + str(e))
                self.logger.info("Updating record failed")

    def update_database(self):
        updated_records = 0
        inserted_ids = {
            'phones': {},
            'addresses': {},
            'emails': {}
        }

        while self.scraped_records:
            person = self.scraped_records.pop(0)
            try:
                if person['scraper_level'] != 3:
                    self.update_scraper_level(person)
                    self.sql_connection.commit()
                    updated_records += 1
                    continue

                self.update_person(person)
                self.insert_addresses(person, inserted_ids['addresses'])
                self.insert_phones(person, inserted_ids['phones'])
                self.insert_emails(person, inserted_ids['emails'])
                self.update_scraper_level(person)

                self.sql_connection.commit()
                updated_records += 1

            except Exception as e:
                self.logger.info(e)

        self.logger.info('scraped and stored {} records'.format(updated_records))

    def get_address_parts(self, person):
        address_keys = ['mailing_address', 'property_address']
        address_parts = []

        for a_key in address_keys:
            address = person.get(a_key, '').lower()
            for value, key in usaddress.parse(address):
                if key == 'AddressNumber' or key == 'StreetName':
                    value = value.replace(',', '') + ' '
                    if value and value.strip():
                        address_parts.append(value)

        address_parts = set(address_parts)
        return address_parts

    def contain_name(self, item, name):
        name = name.lower().strip()
        last_name = item['last_name'].lower().strip()
        first_name = item['first_name'].lower().strip()
        first_names = [first_name] + self.nick_names.get(first_name, [])

        return last_name in name and (any(fn.lower() in name for fn in first_names) or first_name[0] == name[0])

    nick_names = {
        'augustina': ['augustina', 'tina', 'aggy', 'gatsy', 'gussie'],
        'lias': ['elias', 'eli', 'lee', 'lias'],
        'augustine': ['augustine', 'gus', 'austin', 'august'],
        'ali': ['alison', 'ali'],
        'conny': ['cornelius', 'conny', 'niel', 'corny', 'con'],
        'monte': ['monteleon', 'monte'],
        'blanche': ['blanche', 'bea'],
        'arminta': ['arminta', 'minite', 'minnie'],
        'cameron': ['cameron', 'ron', 'cam', 'ronny'],
        'woody': ['woodrow', 'woody', 'wood', 'drew'],
        'gabriella': ['gabriella', 'ella', 'gabby'],
        'gabrielle': ['gabrielle', 'ella', 'gabby'],
        'emily': ['emily', 'emmy', 'millie', 'emma', 'mel'],
        'ozzy': ['waldo', 'ozzy', 'ossy'],
        'jessie': ['jessie', 'jane', 'jess', 'janet'],
        'sanford': ['sanford', 'sandy'],
        'franniey': ['francine', 'franniey', 'fran', 'frannie', 'francie'],
        'unice': ['unice', 'eunice', 'nicie'],
        'trixie': ['trix', 'trixie'],
        'aaron': ['aaron', 'erin', 'ronnie', 'ron'],
        'edward': ['edward', 'teddy', 'ed', 'ned', 'ted', 'eddy', 'eddie'],
        'danielle': ['danielle', 'ellie', 'dani'],
        'elias': ['elias', 'eli', 'lee', 'lias'],
        'alberta': ['alberta', 'bert', 'allie', 'bertie'],
        'ren': ['lauren', 'ren', 'laurie'],
        'eleazer': ['eleazer', 'lazar'],
        'reggie': ['reginald', 'reggie', 'naldo', 'reg', 'renny'],
        'cynthia': ['cynthia', 'cintha', 'cindy'],
        'vert': ['alverta', 'virdie', 'vert'],
        'artelepsa': ['artelepsa', 'epsey'],
        'delf': ['delphine', 'delphi', 'del', 'delf'],
        'callie': ['california', 'callie'],
        'dutch': ['herman', 'harman', 'dutch'],
        'penny': ['penelope', 'penny'],
        'dell': ['delores', 'lolly', 'lola', 'della', 'dee', 'dell'],
        'lanna': ['eleanor', 'lanna', 'nora', 'nelly', 'ellie', 'elaine', 'ellen', 'lenora'],
        'wilfred': ['wilfred', 'will', 'willie', 'fred'],
        'senie': ['eseneth', 'senie'],
        'jacob': ['jacobus', 'jacob'],
        'elena': ['elena', 'helen'],
        'leonidas': ['leonidas', 'lee', 'leon'],
        'zolly': ['solomon', 'sal', 'salmon', 'sol', 'solly', 'saul', 'zolly'],
        'hessy': ['hester', 'hessy', 'esther', 'hetty'],
        'broderick': ['broderick', 'ricky', 'brody', 'brady', 'rick'],
        'louis': ['louis', 'lewis', 'louise', 'louie', 'lou'],
        'rosalyn': ['roz', 'rosalyn'],
        'herbert': ['herbert', 'bert', 'herb'],
        'lish': ['elisha', 'lish', 'eli'],
        'zadie': ['isaiah', 'zadie', 'zay'],
        'harry': ['henry', 'hank', 'hal', 'harry'],
        'delilah': ['della', 'adela', 'delilah', 'adelaide'],
        'lisa': ['melissa', 'lisa', 'mel', 'missy', 'milly', 'lissa'],
        'harriet': ['harriet', 'hattie'],
        'parthenia': ['parthenia', 'teeny', 'parsuny', 'pasoonie', 'phenie'],
        'vincenzo': ['vincenzo', 'vic', 'vinnie', 'vin', 'vinny'],
        'wilber': ['wilber', 'will', 'bert'],
        'eileen': ['helena', 'eileen', 'lena', 'nell', 'nellie', 'eleanor', 'elaine', 'ellen', 'aileen'],
        'dunk': ['duncan', 'dunk'],
        'chet': ['chet', 'chester'],
        'valeri': ['valeri', 'val'],
        'cher': ['cher', 'sher'],
        'ted': ['theodore', 'theo', 'ted', 'teddy'],
        'cissy': ['priscilla', 'prissy', 'cissy', 'cilla'],
        'philomena': ['philomena', 'menaalmena'],
        'torie': ['victoria', 'torie', 'vic', 'vicki', 'tory', 'vicky'],
        'rusty': ['rusty', 'russell'],
        'cornelia': ['cornelia', 'nelly', 'cornie', 'nelia', 'corny', 'nelle'],
        'silvester': ['silvester', 'vester', 'si', 'sly', 'vest', 'syl'],
        'melvin': ['melvin', 'mel'],
        'titia': ['letitia', 'tish', 'titia', 'lettice', 'lettie'],
        'hitty': ['mehitabel', 'hetty', 'mitty', 'mabel', 'hitty'],
        'sue': ['suzanne', 'suki', 'sue', 'susie'],
        'abe': ['abraham', 'ab', 'abe'],
        'richard': ['richie', 'richard'],
        'nana': ['anne', 'annie', 'nana', 'ann', 'nan', 'nanny', 'nancy'],
        'ned': ['edwin', 'ed', 'eddie', 'win', 'eddy', 'ned'],
        'fidelia': ['fidelia', 'delia'],
        'shelly': ['shelton', 'tony', 'shel', 'shelly'],
        'natius': ['ignatius', 'natius', 'iggy', 'nate', 'nace'],
        'minty': ['araminta', 'armida', 'middie', 'ruminta', 'minty'],
        'monty': ['monty', 'lamont'],
        'lizzie': ['lizzie', 'elizabeth', 'liz'],
        'antoinette': ['antoinette', 'tony', 'netta', 'ann'],
        'deborah': ['deborah', 'deb', 'debbie', 'debby'],
        'maud': ['maud', 'middy'],
        'meg': ['megan', 'meg'],
        'christian': ['christian', 'chris', 'kit'],
        'dahl': ['dalton', 'dahl'],
        'zach': ['zachariah', 'zachy', 'zach', 'zeke'],
        'micajah': ['micajah', 'cage'],
        'mel': ['melvin', 'mel'],
        'eunice': ['unice', 'eunice', 'nicie'],
        'theresa': ['theresa', 'tessie', 'thirza', 'tessa', 'terry', 'tracy', 'tess', 'thursa'],
        'drew': ['woodrow', 'woody', 'wood', 'drew'],
        'christa': ['christa', 'chris'],
        'beck': ['rebecca', 'beck', 'becca', 'reba', 'becky'],
        'dora': ['theodora', 'dora'],
        'nanny': ['nancy', 'ann', 'nan', 'nanny'],
        'christy': ['kristine', 'kris', 'kristy', 'tina', 'christy', 'chris', 'crissy'],
        'drea': ['andrea', 'drea', 'rea', 'andrew'],
        'lotta': ['lotta', 'lottie'],
        'barnabas': ['barney', 'barnabas'],
        'gerry': ['gerry', 'gerald', 'geraldine', 'jerry'],
        'luther': ['luther', 'luke'],
        'vicky': ['victoria', 'torie', 'vic', 'vicki', 'tory', 'vicky'],
        'mavery': ['mavery', 'mave'],
        'tranquilla': ['tranquilla', 'trannie', 'quilla'],
        'myrt': ['myrtle', 'myrt', 'myrti', 'mert'],
        'medora': ['medora', 'dora'],
        'cordelia': ['delia', 'fidelia', 'cordelia', 'delius'],
        'experience': ['experience', 'exie'],
        'stella': ['estelle', 'essy', 'stella'],
        'vannie': ['vandalia', 'vannie'],
        'delphine': ['delphine', 'delphi', 'del', 'delf'],
        'agatha': ['agatha', 'aggy'],
        'cindy': ['lucinda', 'lu', 'lucy', 'cindy', 'lou'],
        'cathy': ['kathleen', 'kathy', 'katy', 'lena', 'kittie', 'kit', 'trina', 'cathy', 'kay', 'cassie'],
        'raze': ['erasmus', 'raze', 'rasmus'],
        'myra': ['samyra', 'myra'],
        'joshua': ['joshua', 'jos', 'josh'],
        'archie': ['archibald', 'archie'],
        'alexandria': ['alexandria', 'drina', 'alexander', 'alla', 'sandra'],
        'sonnie': ['sondra', 'dre', 'sonnie'],
        'carmellia': ['carmellia', 'mellia'],
        'julie': ['julie', 'julia', 'jule'],
        'donnie': ['donnie', 'donald', 'donny'],
        'vin': ['vincenzo', 'vic', 'vinnie', 'vin', 'vinny'],
        'letitia': ['letitia', 'tish', 'titia', 'lettice', 'lettie'],
        'maisie': ['margarita', 'maggie', 'meg', 'metta', 'midge', 'greta', 'megan', 'maisie', 'madge', 'marge',
                   'daisy', 'peggie', 'rita', 'margo'],
        'lonzo': ['lon', 'lonzo'],
        'patience': ['patience', 'pat', 'patty'],
        'dortha': ['dorothy', 'dortha', 'dolly', 'dot', 'dotty'],
        'viv': ['vivian', 'vi', 'viv'],
        'tashie': ['tasha', 'tash', 'tashie'],
        'dre': ['sondra', 'dre', 'sonnie'],
        'sene': ['asenath', 'sene', 'assene', 'natty'],
        'florence': ['florence', 'flossy', 'flora', 'flo'],
        'tempy': ['temperance', 'tempy'],
        'clifford': ['clifford', 'ford', 'cliff'],
        'sarah': ['sarah', 'sally', 'sadie'],
        'jayme': ['jayme', 'jay'],
        'kittie': ['kit', 'kittie'],
        'cornie': ['cornelia', 'nelly', 'cornie', 'nelia', 'corny', 'nelle'],
        'rafa': ['rafaela', 'rafa'],
        'nora': ['nora', 'nonie'],
        'mort': ['mortimer', 'mort'],
        'vi': ['vivian', 'vi', 'viv'],
        'winny': ['winny', 'winnifred'],
        'lorry': ['lawrence', 'lorry', 'larry', 'lon', 'lonny', 'lorne'],
        'freda': ['fredericka', 'freddy', 'ricka', 'freda', 'frieda'],
        'percy': ['percival', 'percy'],
        'yulan': ['yulan', 'lan', 'yul'],
        'odell': ['odell', 'odo'],
        'mira': ['miranda', 'randy', 'mandy', 'mira'],
        'leonard': ['leonard', 'lineau', 'leo', 'leon', 'len', 'lenny'],
        'mathew': ['matt', 'mathew', 'matthew'],
        'floyd': ['floyd', 'lloyd'],
        'berney': ['berney', 'bernie'],
        'feli': ['felicia', 'fel', 'felix', 'feli'],
        'kendra': ['kendra', 'kenj', 'kenji', 'kay', 'kenny'],
        'debora': ['debora', 'deb', 'debbie', 'debby'],
        'onie': ['yeona', 'onie', 'ona'],
        'arabella': ['bella', 'belle', 'arabella', 'isabella'],
        'flora': ['florence', 'flossy', 'flora', 'flo'],
        'mc': ['mack', 'mac', 'mc'],
        'elysia': ['elysia', 'lisa'],
        'phillip': ['phillip', 'phil'],
        'sylvanus': ['sylvanus', 'sly', 'syl'],
        'nappy': ['napoleon', 'nap', 'nappy', 'leon'],
        'orilla': ['orilla', 'rilly', 'ora'],
        'del': ['delphine', 'delphi', 'del', 'delf'],
        'hermione': ['hermione', 'hermie'],
        'kristopher': ['kristopher', 'chris', 'kris'],
        'dea': ['demerias', 'dea', 'maris', 'mary'],
        'deb': ['debra', 'deb', 'debbie'],
        'dee': ['delores', 'lolly', 'lola', 'della', 'dee', 'dell'],
        'abram': ['abram', 'ab'],
        'lavina': ['lavina', 'vina', 'viney', 'ina'],
        'hallie': ['mahala', 'hallie'],
        'barbery': ['barbery', 'barbara'],
        'theodosia': ['theodosia', 'theo', 'dosia', 'theodosius'],
        'micky': ['mike', 'micky', 'mick', 'michael'],
        'honey': ['honora', 'honey', 'nora', 'norry', 'norah'],
        'abner': ['abner', 'ab'],
        'iona': ['iona', 'onnie'],
        'armilda': ['armilda', 'milly'],
        'harold': ['harry', 'harold', 'henry'],
        'zachariah': ['zachariah', 'zachy', 'zach', 'zeke'],
        'onicyphorous': ['onicyphorous', 'cyphorus', 'osaforus', 'syphorous', 'one', 'cy', 'osaforum'],
        'assene': ['asenath', 'sene', 'assene', 'natty'],
        'smitty': ['smith', 'smitty'],
        'joann': ['joann', 'jo'],
        'court': ['courtney', 'curt', 'court'],
        'lura': ['lurana', 'lura'],
        'elbert': ['elbertson', 'elbert', 'bert'],
        'elswood': ['elswood', 'elsey'],
        'hugh': ['jehu', 'hugh', 'gee'],
        'tilford': ['tilford', 'tillie'],
        'dilly': ['deliverance', 'delly', 'dilly', 'della'],
        'armena': ['armena', 'mena', 'arry'],
        'hop': ['hopkins', 'hopp', 'hop'],
        'ronnie': ['veronica', 'vonnie', 'ron', 'ronna', 'ronie', 'frony', 'franky', 'ronnie'],
        'obadiah': ['obadiah', 'dyer', 'obed', 'obie', 'diah'],
        'lan': ['yulan', 'lan', 'yul'],
        'becky': ['rebecca', 'beck', 'becca', 'reba', 'becky'],
        'elizabeth': ['lizzie', 'elizabeth', 'liz'],
        'yeona': ['yeona', 'onie', 'ona'],
        'pokey': ['pocahontas', 'pokey'],
        'judie': ['judith', 'judie', 'juda', 'judy', 'judi', 'jude'],
        'arthusa': ['arthusa', 'thursa'],
        'edyth': ['edyth', 'edie', 'edye'],
        'rudy': ['rudy', 'rudolph'],
        'pherbia': ['pheriba', 'pherbia', 'ferbie'],
        'pasoonie': ['parthenia', 'teeny', 'parsuny', 'pasoonie', 'phenie'],
        'regina': ['regina', 'reggie', 'gina'],
        'philipina': ['philipina', 'phoebe', 'penie'],
        'danny': ['sheridan', 'dan', 'danny', 'sher'],
        'brady': ['broderick', 'ricky', 'brody', 'brady', 'rick'],
        'rosalinda': ['rosalinda', 'linda', 'roz', 'rosa', 'rose'],
        'susan': ['susan', 'hannah', 'susie', 'sue', 'sukey', 'suzie'],
        'leroy': ['leroy', 'roy', 'lee', 'l.r.'],
        'wint': ['winton', 'wint'],
        'dolph': ['rudolphus', 'dolph', 'rudy', 'olph', 'rolf'],
        'rosabella': ['rosabella', 'belle', 'roz', 'rosa', 'rose'],
        'green': ['greenberry', 'green', 'berry'],
        'barby': ['barbara', 'barby', 'babs', 'bab', 'bobbie'],
        'avarilla': ['avarilla', 'rilla'],
        'evaline': ['evaline', 'eva', 'lena', 'eve'],
        'davey': ['david', 'dave', 'day', 'davey'],
        'jack': ['john', 'jack', 'johnny', 'jock'],
        'zeb': ['zebedee', 'zeb'],
        'zed': ['zedediah', 'dyer', 'zed', 'diah'],
        'cenia': ['laodicia', 'dicy', 'cenia'],
        'fifi': ['phoebe', 'fifi'],
        'emmanuel': ['immanuel', 'manuel', 'emmanuel'],
        'bella': ['isabelle', 'tibbie', 'nib', 'belle', 'bella', 'nibby', 'ib', 'issy'],
        'helena': ['helena', 'eileen', 'lena', 'nell', 'nellie', 'eleanor', 'elaine', 'ellen', 'aileen'],
        'muriel': ['muriel', 'mur'],
        'helene': ['helene', 'lena', 'ella', 'ellen', 'ellie'],
        'mabel': ['mehitabel', 'hetty', 'mitty', 'mabel', 'hitty'],
        'oswald': ['ozzy', 'oswald'],
        'tiffy': ['tiffany', 'tiff', 'tiffy'],
        'ebenezer': ['ebenezer', 'ebbie', 'eben', 'eb'],
        'cammie': ['carmon', 'charm', 'cammie', 'carm'],
        'leanne': ['leanne', 'lea', 'annie'],
        'clo': ['chloe', 'clo'],
        'monnie': ['monica', 'monna', 'monnie'],
        'alla': ['alexandria', 'drina', 'alexander', 'alla', 'sandra'],
        'edith': ['edith', 'edie', 'edye'],
        'uriah': ['uriah', 'riah'],
        'ricardo': ['ricardo', 'rick', 'ricky'],
        'dolly': ['dorothy', 'dortha', 'dolly', 'dot', 'dotty'],
        'fie': ['philander', 'fie'],
        'isaac': ['isaac', 'ike', 'zeke'],
        'violetta': ['violetta', 'lettie'],
        'retta': ['loretta', 'etta', 'lorrie', 'retta'],
        'ally': ['alyssa', 'lissia', 'al', 'ally'],
        'eugene': ['eugene', 'gene'],
        'theo': ['theodosia', 'theo', 'dosia', 'theodosius'],
        'ced': ['cedric', 'ced', 'rick', 'ricky'],
        'curtis': ['curtis', 'curt'],
        'viola': ['viola', 'ola', 'vi'],
        'aurilla': ['aurelia', 'ree', 'rilly', 'orilla', 'aurilla', 'ora'],
        'olivia': ['olivia', 'nollie', 'livia', 'ollie'],
        'stephanie': ['stephanie', 'stephen', 'stephie', 'annie', 'steph'],
        'dickson': ['dickson', 'dick'],
        'samson': ['samson', 'sam'],
        'wally': ['walter', 'wally', 'walt'],
        'one': ['onicyphorous', 'cyphorus', 'osaforus', 'syphorous', 'one', 'cy', 'osaforum'],
        'bryan': ['brian', 'bryan', 'bryant'],
        'alex': ['alexandra', 'alex', 'sandy', 'alla', 'sandra'],
        'waldo': ['waldo', 'ozzy', 'ossy'],
        'lillian': ['lillian', 'lil', 'lilly', 'lolly'],
        'johannah': ['johannah', 'hannah', 'jody', 'joan', 'nonie'],
        'chuck': ['chick', 'charlotte', 'caroline', 'chuck'],
        'alexis': ['alexis', 'lexi'],
        'denny': ['dennison', 'denny'],
        'eleanor': ['helena', 'eileen', 'lena', 'nell', 'nellie', 'eleanor', 'elaine', 'ellen', 'aileen'],
        'val': ['valerie', 'val'],
        'anastasia': ['anastasia', 'ana', 'stacy'],
        'providence': ['providence', 'provy'],
        'lige': ['elijah', 'lige', 'eli'],
        'jehiel': ['jehiel', 'hiel'],
        'nicie': ['unice', 'eunice', 'nicie'],
        'domenic': ['domenic', 'dom'],
        'diana': ['diana', 'dicey', 'didi', 'di'],
        'ollie': ['ollie', 'oliver'],
        'tiffany': ['tiffany', 'tiff', 'tiffy'],
        'tamarra': ['tamarra', 'tammy'],
        'diane': ['diane', 'dicey', 'didi', 'di'],
        'allan': ['allan', 'al'],
        'zebedee': ['zebedee', 'zeb'],
        'alanson': ['alanson', 'al', 'lanson'],
        'elwood': ['elwood', 'woody'],
        'gum': ['montgomery', 'monty', 'gum'],
        'doug': ['douglas', 'doug'],
        'randolph': ['randolph', 'dolph', 'randy'],
        'meaka': ['mckenna', 'ken', 'kenna', 'meaka'],
        'lola': ['delores', 'lolly', 'lola', 'della', 'dee', 'dell'],
        'arielle': ['arielle', 'arie'],
        'ernie': ['ernest', 'ernie'],
        'daph': ['daphne', 'daph', 'daphie'],
        'robert': ['robert', 'hob', 'hobkin', 'dob', 'rob', 'bobby', 'dobbin', 'bob'],
        'syd': ['sidney', 'syd', 'sid'],
        'mandy': ['miranda', 'randy', 'mandy', 'mira'],
        'ry': ['ryan', 'ry'],
        'douglas': ['douglas', 'doug'],
        'renny': ['reginald', 'reggie', 'naldo', 'reg', 'renny'],
        'si': ['sylvester', 'sy', 'sly', 'vet', 'syl', 'vester', 'si', 'vessie'],
        'nita': ['juanita', 'nita', 'nettie'],
        'daniel': ['danny', 'daniel'],
        'manda': ['manda', 'mandy'],
        'jemima': ['jemima', 'mima'],
        'judith': ['judy', 'judith'],
        'benjamin': ['benjy', 'benjamin'],
        'lineau': ['leonard', 'lineau', 'leo', 'leon', 'len', 'lenny'],
        'arizona': ['arizona', 'onie', 'ona'],
        'jeremiah': ['jeremiah', 'jereme', 'jerry'],
        'lawrence': ['lawrence', 'lorry', 'larry', 'lon', 'lonny', 'lorne'],
        'tasha': ['tasha', 'tash', 'tashie'],
        'rickie': ['roderick', 'rod', 'erick', 'rickie'],
        'fred': ['winnifred', 'freddie', 'freddy', 'winny', 'winnie', 'fred'],
        'pleasant': ['pleasant', 'ples'],
        'kayla': ['kayla', 'kay'],
        'asa': ['asaph', 'asa'],
        'jennie': ['virginia', 'jane', 'jennie', 'ginny', 'virgy', 'ginger'],
        'euphemia': ['euphemia', 'effie', 'effy'],
        'stacy': ['eustacia', 'stacia', 'stacy'],
        'bartholomew': ['bartholomew', 'bartel', 'bat', 'meus', 'bart', 'mees'],
        'nonie': ['nora', 'nonie'],
        'benjy': ['benjy', 'benjamin'],
        'dorinda': ['dorinda', 'dorothea', 'dora'],
        'birdie': ['roberta', 'robbie', 'bert', 'bobbie', 'birdie', 'bertie'],
        'debby': ['deborah', 'deb', 'debbie', 'debby'],
        'lucina': ['lucina', 'sinah'],
        'juder': ['judah', 'juder', 'jude'],
        'nowell': ['nowell', 'noel'],
        'sondra': ['sondra', 'dre', 'sonnie'],
        'lavinia': ['lavinia', 'vina', 'viney', 'ina'],
        'daisy': ['margarita', 'maggie', 'meg', 'metta', 'midge', 'greta', 'megan', 'maisie', 'madge', 'marge', 'daisy',
                  'peggie', 'rita', 'margo'],
        'magdalena': ['magdalena', 'maggie', 'lena'],
        'kendrick': ['kent', 'ken', 'kenny', 'kendrick'],
        'flick': ['felicity', 'flick', 'tick'],
        'bridgie': ['bridget', 'bridie', 'biddy', 'bridgie', 'biddie'],
        'dina': ['geraldine', 'gerry', 'gerrie', 'jerry', 'dina'],
        'nace': ['ignatzio', 'naz', 'iggy', 'nace'],
        'dony': ['donald', 'dony', 'donnie', 'don', 'donny'],
        'valentina': ['valentina', 'felty', 'vallie', 'val'],
        'obedience': ['obedience', 'obed', 'beda', 'beedy', 'biddie'],
        'gustavus': ['gustavus', 'gus'],
        'wash': ['washington', 'wash'],
        'bridgit': ['bedelia', 'delia', 'bridgit'],
        'tanny': ['tanafra', 'tanny'],
        'mervyn': ['mervyn', 'merv'],
        'timothy': ['timothy', 'tim', 'timmy'],
        'jefferey': ['jefferey', 'jeff'],
        'amos': ['moses', 'amos', 'mose', 'moss'],
        'benedict': ['benedict', 'bennie', 'ben'],
        'deanne': ['deanne', 'ann', 'dee'],
        'eddy': ['edwin', 'ed', 'eddie', 'win', 'eddy', 'ned'],
        'peggie': ['margarita', 'maggie', 'meg', 'metta', 'midge', 'greta', 'megan', 'maisie', 'madge', 'marge',
                   'daisy', 'peggie', 'rita', 'margo'],
        'jeb': ['jeb', 'jebadiah'],
        'bazaleel': ['bazaleel', 'basil'],
        'magda': ['magdelina', 'lena', 'magda', 'madge'],
        'jed': ['jedidiah', 'jed'],
        'tom': ['tom', 'thomas', 'tommy'],
        'gilbert': ['gilbert', 'bert', 'gil', 'wilber'],
        'john': ['jonathan', 'john', 'nathan'],
        'sibbie': ['sybill', 'sibbie'],
        'killis': ['archilles', 'kill', 'killis'],
        'jem': ['james', 'jimmy', 'jim', 'jamie', 'jimmie', 'jem'],
        'naldo': ['ronald', 'naldo', 'ron', 'ronny'],
        'roge': ['roger', 'roge', 'bobby', 'hodge', 'rod', 'robby', 'rupert', 'robin'],
        'nickie': ['nickie', 'nicholas'],
        'dacey': ['candace', 'candy', 'dacey'],
        'lissia': ['alyssa', 'lissia', 'al', 'ally'],
        'albert': ['elbert', 'albert'],
        'eudicy': ['eudicy', 'dicey'],
        'crate': ['socrates', 'crate'],
        'helen': ['helen', 'lena', 'ella', 'ellen', 'ellie'],
        'gretchen': ['gretchen', 'margaret'],
        'ernestine': ['ernestine', 'teeny', 'ernest', 'tina', 'erna'],
        'winton': ['winton', 'wint'],
        'gertie': ['gertrude', 'gertie', 'gert', 'trudy'],
        'karon': ['karonhappuck', 'karon', 'karen', 'carrie', 'happy'],
        'mercy': ['mercedes', 'merci', 'sadie', 'mercy'],
        'pinckney': ['pinckney', 'pink'],
        'jahoda': ['jahoda', 'hody', 'hodie', 'hoda'],
        'asaph': ['asaph', 'asa'],
        'kenji': ['kendra', 'kenj', 'kenji', 'kay', 'kenny'],
        'silla': ['sarilla', 'silla'],
        'sceeter': ['scott', 'scotty', 'sceeter', 'squat', 'scottie'],
        'roseann': ['roseann', 'rose', 'ann', 'rosie', 'roz'],
        'merci': ['mercedes', 'merci', 'sadie', 'mercy'],
        'libby': ['lib', 'libby'],
        'greg': ['gregory', 'greg'],
        'dani': ['danielle', 'ellie', 'dani'],
        'zephaniah': ['zephaniah', 'zeph'],
        'prescott': ['prescott', 'scotty', 'scott', 'pres'],
        'trisha': ['trisha', 'patricia'],
        'mickey': ['michelle', 'mickey'],
        'charlotte': ['chick', 'charlotte', 'caroline', 'chuck'],
        'leafa': ['relief', 'leafa'],
        'creasey': ['lucretia', 'creasey'],
        'reginald': ['reynold', 'reginald'],
        'odo': ['odell', 'odo'],
        'caleb': ['caleb', 'cal'],
        'ginger': ['virginia', 'jane', 'jennie', 'ginny', 'virgy', 'ginger'],
        'liley': ['silence', 'liley'],
        'corny': ['cornelius', 'conny', 'niel', 'corny', 'con'],
        'telly': ['aristotle', 'telly'],
        'lula': ['luella', 'lula', 'ella', 'lu'],
        'philly': ['philly', 'delphia'],
        'ferdie': ['ferdinando', 'nando', 'ferdie', 'fred'],
        'ray': ['raymond', 'ray'],
        'dickie': ['richard', 'dick', 'dickon', 'dickie', 'dicky', 'rick', 'rich', 'ricky'],
        'wilson': ['wilson', 'will', 'willy', 'willie'],
        'winnifred': ['winny', 'winnifred'],
        'jule': ['julie', 'julia', 'jule'],
        'lib': ['lib', 'libby'],
        'judah': ['judah', 'juder', 'jude'],
        'lil': ['lillian', 'lil', 'lilly', 'lolly'],
        'kaye': ['katherine', 'kathy', 'katy', 'lena', 'kittie', 'kaye', 'kit', 'trina', 'cathy', 'kay', 'kate',
                 'cassie'],
        'scott': ['scott', 'scotty', 'sceeter', 'squat', 'scottie'],
        'karonhappuck': ['karonhappuck', 'karon', 'karen', 'carrie', 'happy'],
        'becca': ['rebecca', 'beck', 'becca', 'reba', 'becky'],
        'bobbie': ['roberta', 'robbie', 'bert', 'bobbie', 'birdie', 'bertie'],
        'sherry': ['shirley', 'sherry', 'lee', 'shirl'],
        'ditus': ['epaphroditius', 'dite', 'ditus', 'eppa', 'dyche', 'dyce'],
        'liz': ['lizzie', 'elizabeth', 'liz'],
        'mose': ['moses', 'amos', 'mose', 'moss'],
        'serene': ['cyrenius', 'swene', 'cy', 'serene', 'renius', 'cene'],
        'jamie': ['jamie', 'james'],
        'susie': ['suzanne', 'suki', 'sue', 'susie'],
        'lettice': ['letitia', 'tish', 'titia', 'lettice', 'lettie'],
        'serena': ['serena', 'rena'],
        'ronna': ['veronica', 'vonnie', 'ron', 'ronna', 'ronie', 'frony', 'franky', 'ronnie'],
        'essy': ['estelle', 'essy', 'stella'],
        'salmon': ['solomon', 'sal', 'salmon', 'sol', 'solly', 'saul', 'zolly'],
        'maris': ['demerias', 'dea', 'maris', 'mary'],
        'maddy': ['madison', 'mattie', 'maddy'],
        'lamont': ['monty', 'lamont'],
        'freddie': ['winnifred', 'freddie', 'freddy', 'winny', 'winnie', 'fred'],
        'pamela': ['pamela', 'pam'],
        'norry': ['honora', 'honey', 'nora', 'norry', 'norah'],
        'charm': ['carmon', 'charm', 'cammie', 'carm'],
        'moss': ['moses', 'amos', 'mose', 'moss'],
        'sandra': ['sandy', 'sandra'],
        'daphne': ['daphne', 'daph', 'daphie'],
        'kay': ['kendra', 'kenj', 'kenji', 'kay', 'kenny'],
        'marie': ['marietta', 'mariah', 'mercy', 'polly', 'may', 'molly', 'mitzi', 'minnie', 'mollie', 'mae', 'maureen',
                  'marion', 'marie', 'mamie', 'mary', 'maria'],
        'mack': ['mackenzie', 'kenzy', 'mac', 'mack'],
        'jean': ['jeanette', 'jessie', 'jean', 'janet', 'nettie'],
        'ronny': ['ronny', 'ronald'],
        'arly': ['arlene', 'arly', 'lena'],
        'don': ['donald', 'dony', 'donnie', 'don', 'donny'],
        'diah': ['zedediah', 'dyer', 'zed', 'diah'],
        'dom': ['dominic', 'dom'],
        'dob': ['robert', 'hob', 'hobkin', 'dob', 'rob', 'bobby', 'dobbin', 'bob'],
        'carmon': ['carmon', 'charm', 'cammie', 'carm'],
        'kris': ['kristopher', 'chris', 'kris'],
        'cleat': ['cleatus', 'cleat'],
        'vicki': ['victoria', 'torie', 'vic', 'vicki', 'tory', 'vicky'],
        'sheryl': ['sheryl', 'sher'],
        'alazama': ['alazama', 'ali'],
        'chester': ['chet', 'chester'],
        'gabe': ['gabriel', 'gabe', 'gabby'],
        'mildred': ['mildred', 'milly'],
        'kristel': ['kristel', 'kris'],
        'dot': ['dot', 'dotty'],
        'agnes': ['inez', 'agnes'],
        'joey': ['josephine', 'fina', 'jody', 'jo', 'josey', 'joey'],
        'vanburen': ['vanburen', 'buren'],
        'mahala': ['mahala', 'hallie'],
        'frances': ['frances', 'sis', 'cissy', 'frankie', 'franniey', 'fran', 'francie', 'frannie', 'fanny'],
        'phoebe': ['phoebe', 'fifi'],
        'lewis': ['louis', 'lewis', 'louise', 'louie', 'lou'],
        'effy': ['euphemia', 'effie', 'effy'],
        'teresa': ['tessa', 'teresa', 'theresa'],
        'liza': ['elizabeth', 'libby', 'lisa', 'lib', 'lizzie', 'eliza', 'betsy', 'liza', 'betty', 'bessie', 'bess',
                 'beth', 'liz'],
        'dyche': ['epaphroditius', 'dite', 'ditus', 'eppa', 'dyche', 'dyce'],
        'bartel': ['bartholomew', 'bartel', 'bat', 'meus', 'bart', 'mees'],
        'carrie': ['karonhappuck', 'karon', 'karen', 'carrie', 'happy'],
        'melody': ['melody', 'lodi'],
        'deedee': ['nadine', 'nada', 'deedee'],
        'louisa': ['louisa', 'eliza', 'lou', 'lois'],
        'louise': ['louise', 'eliza', 'lou', 'lois'],
        'adaline': ['adaline', 'delia', 'lena', 'dell', 'addy', 'ada'],
        'aldo': ['aldo', 'al'],
        'artemus': ['artemus', 'art'],
        'randy': ['randolph', 'dolph', 'randy'],
        'vinny': ['vinson', 'vinny'],
        'rich': ['ricky', 'dick', 'rich'],
        'rosina': ['rosina', 'sina'],
        'moses': ['moses', 'amos', 'mose', 'moss'],
        'mena': ['armena', 'mena', 'arry'],
        'hodie': ['jahoda', 'hody', 'hodie', 'hoda'],
        'monica': ['monica', 'monna', 'monnie'],
        'tricia': ['patricia', 'tricia', 'pat', 'patsy', 'patty'],
        'roseanne': ['roseanne', 'ann'],
        'cecilia': ['sheila', 'cecilia'],
        'king': ['kingston', 'king'],
        'vinson': ['vinson', 'vinny'],
        'luke': ['luther', 'luke'],
        'alicia': ['alicia', 'lisa', 'elsie', 'allie'],
        'l.r.': ['leroy', 'roy', 'lee', 'l.r.'],
        'christopher': ['christopher', 'chris', 'kit'],
        'lonny': ['lawrence', 'lorry', 'larry', 'lon', 'lonny', 'lorne'],
        'ben': ['benjamin', 'benjy', 'jamie', 'bennie', 'ben'],
        'johanna': ['johanna', 'jo'],
        'sabrina': ['sabrina', 'brina'],
        'jeanne': ['jeanne', 'jane', 'jeannie'],
        'bat': ['bartholomew', 'bartel', 'bat', 'meus', 'bart', 'mees'],
        'sibbell': ['sibbilla', 'sybill', 'sibbie', 'sibbell'],
        'tabby': ['tabitha', 'tabby'],
        'laodicia': ['laodicia', 'dicy', 'cenia'],
        'carlotta': ['carlotta', 'lottie'],
        'bab': ['barbara', 'barby', 'babs', 'bab', 'bobbie'],
        'dyce': ['epaphroditius', 'dite', 'ditus', 'eppa', 'dyche', 'dyce'],
        'arilla': ['cinderella', 'arilla', 'rella', 'cindy', 'rilla'],
        'vincent': ['vincent', 'vic', 'vince', 'vinnie', 'vin', 'vinny'],
        'olph': ['rudolphus', 'dolph', 'rudy', 'olph', 'rolf'],
        'crys': ['crystal', 'chris', 'tal', 'stal', 'crys'],
        'art': ['arthur', 'art'],
        'bart': ['barticus', 'bart'],
        'maurice': ['maurice', 'morey'],
        'vina': ['melvina', 'vina'],
        'wyncha': ['louvinia', 'vina', 'vonnie', 'wyncha', 'viney'],
        'lodi': ['melody', 'lodi'],
        'ara': ['arabelle', 'ara', 'bella', 'arry', 'belle'],
        'geoff': ['jeffrey', 'geoff', 'jeff'],
        'elnora': ['elnora', 'nora'],
        'leslie': ['leslie', 'les'],
        'seb': ['sebastian', 'sebby', 'seb'],
        'margaretta': ['marge', 'margery', 'margaret', 'margaretta'],
        'delores': ['delores', 'lolly', 'lola', 'della', 'dee', 'dell'],
        'thys': ['matthias', 'thys', 'matt', 'thias'],
        'bess': ['elizabeth', 'libby', 'lisa', 'lib', 'lizzie', 'eliza', 'betsy', 'liza', 'betty', 'bessie', 'bess',
                 'beth', 'liz'],
        'araminta': ['araminta', 'armida', 'middie', 'ruminta', 'minty'],
        'allie': ['almena', 'mena', 'allie'],
        'lee': ['shirley', 'sherry', 'lee', 'shirl'],
        'pete': ['peter', 'pete', 'pate'],
        'delpha': ['delpha', 'philadelphia'],
        'eudora': ['eudora', 'dora'],
        'mitch': ['mitchell', 'mitch'],
        'harman': ['herman', 'harman', 'dutch'],
        'delphi': ['delphine', 'delphi', 'del', 'delf'],
        'solomon': ['solomon', 'sal', 'salmon', 'sol', 'solly', 'saul', 'zolly'],
        'irv': ['irving', 'irv'],
        'feltie': ['feltie', 'felty'],
        'manola': ['manola', 'nonnie'],
        'melissa': ['missy', 'melissa'],
        'ronie': ['veronica', 'vonnie', 'ron', 'ronna', 'ronie', 'frony', 'franky', 'ronnie'],
        'herb': ['herbert', 'bert', 'herb'],
        'philander': ['philander', 'fie'],
        'rosa': ['rosalyn', 'linda', 'roz', 'rosa', 'rose'],
        'rita': ['margarita', 'maggie', 'meg', 'metta', 'midge', 'greta', 'megan', 'maisie', 'madge', 'marge', 'daisy',
                 'peggie', 'rita', 'margo'],
        'clarinda': ['clarinda', 'clara'],
        'ruminta': ['araminta', 'armida', 'middie', 'ruminta', 'minty'],
        'lexi': ['alexis', 'lexi'],
        'petronella': ['petronella', 'nellie'],
        'omi': ['naomi', 'omi'],
        'erna': ['ernestine', 'teeny', 'ernest', 'tina', 'erna'],
        'vernon': ['laverne', 'vernon', 'verna'],
        'pelegrine': ['pelegrine', 'perry'],
        'ike': ['isaac', 'ike', 'zeke'],
        'marilyn': ['marilyn', 'mary'],
        'newt': ['newt', 'newton'],
        'stu': ['stuart', 'stu'],
        'lyddy': ['lydia', 'lyddy'],
        'edgar': ['edgar', 'ed', 'eddie', 'eddy'],
        'thom': ['thomas', 'thom', 'tommy', 'tom'],
        'juanita': ['juanita', 'nita', 'nettie'],
        'pernetta': ['pernetta', 'nettie'],
        'annie': ['stephanie', 'stephen', 'stephie', 'annie', 'steph'],
        'brad': ['bradford', 'ford', 'brad'],
        'pate': ['peter', 'pete', 'pate'],
        'patty': ['patty', 'patricia'],
        'rena': ['serena', 'rena'],
        'bedelia': ['bedelia', 'delia', 'bridgit'],
        'essa': ['vanessa', 'essa', 'vanna', 'nessa'],
        'jeff': ['jeffrey', 'geoff', 'jeff'],
        'sullivan': ['sully', 'sullivan'],
        'smith': ['smith', 'smitty'],
        'celeste': ['celeste', 'lessie', 'celia'],
        'darlene': ['darlene', 'lena', 'darry'],
        'matty': ['matthew', 'thys', 'matt', 'thias', 'mattie', 'matty'],
        'lauryn': ['lauryn', 'laurie'],
        'mitzie': ['mitzie', 'mittie', 'mitty'],
        'karen': ['karonhappuck', 'karon', 'karen', 'carrie', 'happy'],
        'hephsibah': ['hephsibah', 'hipsie'],
        'suzie': ['susie', 'suzie'],
        'parmelia': ['parmelia', 'amelia', 'milly', 'melia'],
        'cille': ['lucille', 'cille', 'lu', 'lucy', 'lou'],
        'sammy': ['samuel', 'sammy', 'sam'],
        'cilla': ['priscilla', 'prissy', 'cissy', 'cilla'],
        'katarina': ['katarina', 'catherine', 'tina'],
        'priscilla': ['priscilla', 'prissy', 'cissy', 'cilla'],
        'appoline': ['appoline', 'appy', 'appie'],
        'angel': ['angela', 'angelica', 'angelina', 'angel', 'angeline', 'jane', 'angie'],
        'rox': ['roxane', 'rox', 'roxie'],
        'dicky': ['richard', 'dick', 'dickon', 'dickie', 'dicky', 'rick', 'rich', 'ricky'],
        'nonnie': ['manola', 'nonnie'],
        'sal': ['solomon', 'sal', 'salmon', 'sol', 'solly', 'saul', 'zolly'],
        'rasmus': ['erasmus', 'raze', 'rasmus'],
        'johannes': ['johannes', 'jonathan', 'john', 'johnny'],
        'geoffrey': ['jeff', 'geoffrey', 'jeffrey'],
        'tine': ['martine', 'tine'],
        'tina': ['tina', 'christina'],
        'mina': ['wilhelmina', 'mina', 'wilma', 'willie', 'minnie'],
        'elze': ['elze', 'elsey'],
        'sina': ['rosina', 'sina'],
        'zada': ['alzada', 'zada'],
        'walter': ['walter', 'wally', 'walt'],
        'kathy': ['katy', 'kathy'],
        'hosie': ['hosea', 'hosey', 'hosie'],
        'life': ['eliphalel', 'life'],
        'bennie': ['benjamin', 'benjy', 'jamie', 'bennie', 'ben'],
        'sydney': ['sydney', 'sid'],
        'gay': ['gerhardt', 'gay'],
        'ada': ['adeline', 'delia', 'lena', 'dell', 'addy', 'ada'],
        'irving': ['irving', 'irv'],
        'anthony': ['tony', 'anthony'],
        'dave': ['david', 'dave', 'day', 'davey'],
        'rosabel': ['rosabel', 'belle', 'roz', 'rosa', 'rose'],
        'katherine': ['katherine', 'kathy', 'katy', 'lena', 'kittie', 'kaye', 'kit', 'trina', 'cathy', 'kay', 'kate',
                      'cassie'],
        'ferbie': ['pheriba', 'pherbia', 'ferbie'],
        'evelina': ['evelyn', 'evelina', 'ev', 'eve'],
        'aileen': ['helena', 'eileen', 'lena', 'nell', 'nellie', 'eleanor', 'elaine', 'ellen', 'aileen'],
        'parsuny': ['parthenia', 'teeny', 'parsuny', 'pasoonie', 'phenie'],
        'lionel': ['lionel', 'leon'],
        'armida': ['araminta', 'armida', 'middie', 'ruminta', 'minty'],
        'sheridan': ['sheridan', 'dan', 'danny', 'sher'],
        'govie': ['governor', 'govie'],
        'sly': ['sylvester', 'sy', 'sly', 'vet', 'syl', 'vester', 'si', 'vessie'],
        'sampson': ['sampson', 'sam'],
        'delly': ['deliverance', 'delly', 'dilly', 'della'],
        'thomasa': ['thomasa', 'tamzine'],
        'bill': ['willis', 'willy', 'bill'],
        'governor': ['governor', 'govie'],
        'mindie': ['arminda', 'mindie'],
        'julias': ['julias', 'jule'],
        'dominic': ['dominic', 'dom'],
        'claes': ['nicholas', 'nick', 'claes', 'claas'],
        'mitchell': ['mitchell', 'mitch'],
        'robin': ['roger', 'roge', 'bobby', 'hodge', 'rod', 'robby', 'rupert', 'robin'],
        'della': ['rhodella', 'della'],
        'melia': ['parmelia', 'amelia', 'milly', 'melia'],
        'prudy': ['prudy', 'prudence'],
        'salvador': ['salvador', 'sal'],
        'cheryl': ['cheryl', 'sheryl'],
        'archilles': ['archilles', 'kill', 'killis'],
        'von': ['levone', 'von'],
        'jackie': ['jacqueline', 'jackie', 'jack'],
        'elmira': ['elmira', 'ellie', 'elly', 'mira'],
        'jess': ['jessie', 'jane', 'jess', 'janet'],
        'minite': ['arminta', 'minite', 'minnie'],
        'griselda': ['griselda', 'grissel'],
        'ib': ['isabelle', 'tibbie', 'nib', 'belle', 'bella', 'nibby', 'ib', 'issy'],
        'k.c.': ['kasey', 'k.c.'],
        'barney': ['bernard', 'barney', 'bernie', 'berney'],
        'cene': ['cyrenius', 'swene', 'cy', 'serene', 'renius', 'cene'],
        'myrti': ['myrtle', 'myrt', 'myrti', 'mert'],
        'belle': ['rosabella', 'belle', 'roz', 'rosa', 'rose'],
        'shay': ['sharon', 'sha', 'shay'],
        'jerry': ['jerry', 'jereme', 'geraldine'],
        'hester': ['hester', 'hessy', 'esther', 'hetty'],
        'roland': ['roland', 'rollo', 'lanny', 'orlando', 'rolly'],
        'mackenzie': ['mackenzie', 'kenzy', 'mac', 'mack'],
        'loomie': ['salome', 'loomie'],
        'dotha': ['dotha', 'dotty'],
        'millie': ['emily', 'emmy', 'millie', 'emma', 'mel'],
        'cassandra': ['sandra', 'sandy', 'cassandra'],
        'gatsy': ['augustina', 'tina', 'aggy', 'gatsy', 'gussie'],
        'bezaleel': ['bezaleel', 'zeely'],
        'hank': ['henry', 'hank', 'hal', 'harry'],
        'nik': ['nik', 'nick'],
        'asahel': ['asahel', 'asa'],
        'lindy': ['philinda', 'linda', 'lynn', 'lindy'],
        'nib': ['isabelle', 'tibbie', 'nib', 'belle', 'bella', 'nibby', 'ib', 'issy'],
        'ezideen': ['ezideen', 'ez'],
        'ella': ['luella', 'lula', 'ella', 'lu'],
        'theodora': ['theodora', 'dora'],
        'obie': ['obie', 'obediah'],
        'lyndon': ['lyndon', 'lindy', 'lynn'],
        'kit': ['kit', 'kittie'],
        'sephy': ['persephone', 'seph', 'sephy'],
        'elly': ['elmira', 'ellie', 'elly', 'mira'],
        'josey': ['josey', 'josophine'],
        'kim': ['kimberly', 'kim'],
        'janice': ['janice', 'jan'],
        'tash': ['tasha', 'tash', 'tashie'],
        'dite': ['epaphroditius', 'dite', 'ditus', 'eppa', 'dyche', 'dyce'],
        'lucas': ['luke', 'lucas'],
        'earnest': ['earnest', 'ernestine', 'ernie'],
        'nole': ['nicole', 'nole', 'nikki', 'cole'],
        'charlie': ['charlie', 'charles', 'chuck'],
        'jedediah': ['jedediah', 'dyer', 'jed', 'diah'],
        'levi': ['levi', 'lee'],
        'corinne': ['corinne', 'cora', 'ora'],
        'nibby': ['isabelle', 'tibbie', 'nib', 'belle', 'bella', 'nibby', 'ib', 'issy'],
        'eph': ['ephraim', 'eph'],
        'horry': ['horace', 'horry'],
        'josophine': ['josey', 'josophine'],
        'azariah': ['azariah', 'riah', 'aze'],
        'left': ['eliphalet', 'left'],
        'anselm': ['selma', 'anselm'],
        'rudolph': ['rudy', 'rudolph'],
        'pheney': ['pheney', 'josephine'],
        'steven': ['steven', 'steve', 'steph'],
        'vic': ['vincenzo', 'vic', 'vinnie', 'vin', 'vinny'],
        'newton': ['newt', 'newton'],
        'lester': ['lester', 'les'],
        'roderick': ['roderick', 'rod', 'erick', 'rickie'],
        'thaddeus': ['thaddeus', 'thad'],
        'marianna': ['marian', 'marianna', 'marion'],
        'sam': ['samuel', 'sammy', 'sam'],
        'campbell': ['campbell', 'cam'],
        'shaina': ['shaina', 'sha', 'shay'],
        'eli': ['elisha', 'lish', 'eli'],
        'hal': ['howard', 'hal', 'howie'],
        'ham': ['hamilton', 'ham'],
        'adrienne': ['adrienne', 'adrian'],
        'melinda': ['melinda', 'linda', 'mel', 'lynn', 'mindy', 'lindy'],
        'hetty': ['mehitabel', 'hetty', 'mitty', 'mabel', 'hitty'],
        'josh': ['joshua', 'jos', 'josh'],
        'mave': ['mavine', 'mave'],
        'genevieve': ['genevieve', 'jean', 'eve', 'jenny'],
        'trina': ['kathleen', 'kathy', 'katy', 'lena', 'kittie', 'kit', 'trina', 'cathy', 'kay', 'cassie'],
        'greenberry': ['greenberry', 'green', 'berry'],
        'calista': ['calista', 'kissy'],
        'courtney': ['courtney', 'curt', 'court'],
        'duncan': ['duncan', 'dunk'],
        'dorcus': ['dorcus', 'darkey'],
        'minerva': ['minerva', 'minnie'],
        'vanessa': ['vanessa', 'essa', 'vanna', 'nessa'],
        'christina': ['tina', 'christina'],
        'rhynie': ['rhyna', 'rhynie'],
        'julia': ['julie', 'julia', 'jule'],
        'madge': ['margarita', 'maggie', 'meg', 'metta', 'midge', 'greta', 'megan', 'maisie', 'madge', 'marge', 'daisy',
                  'peggie', 'rita', 'margo'],
        'zeely': ['bezaleel', 'zeely'],
        'cleatus': ['cleatus', 'cleat'],
        'mariah': ['marietta', 'mariah', 'mercy', 'polly', 'may', 'molly', 'mitzi', 'minnie', 'mollie', 'mae',
                   'maureen', 'marion', 'marie', 'mamie', 'mary', 'maria'],
        'caldonia': ['caldonia', 'calliedona'],
        'ambrose': ['ambrose', 'brose'],
        'elouise': ['heloise', 'lois', 'eloise', 'elouise'],
        'marian': ['marian', 'marianna', 'marion'],
        'midge': ['margarita', 'maggie', 'meg', 'metta', 'midge', 'greta', 'megan', 'maisie', 'madge', 'marge', 'daisy',
                  'peggie', 'rita', 'margo'],
        'bobby': ['roger', 'roge', 'bobby', 'hodge', 'rod', 'robby', 'rupert', 'robin'],
        'orlando': ['roland', 'rollo', 'lanny', 'orlando', 'rolly'],
        'alice': ['lisa', 'lizzie', 'alice', 'liz', 'melissa'],
        'roseanna': ['roseanna', 'rose', 'ann', 'rosie', 'roz'],
        'steph': ['steven', 'steve', 'steph'],
        'arthur': ['arthur', 'art'],
        'lucretia': ['lucretia', 'creasey'],
        'gwendolyn': ['gwendolyn', 'gwen', 'wendy'],
        'thaney': ['bethena', 'beth', 'thaney'],
        'ivan': ['ivan', 'john'],
        'judson': ['judson', 'sonny', 'jud'],
        'persephone': ['persephone', 'seph', 'sephy'],
        'sebastian': ['sebastian', 'sebby', 'seb'],
        'clementine': ['clementine', 'clement', 'clem'],
        'webb': ['webster', 'webb'],
        'coco': ['cory', 'coco', 'cordy', 'ree'],
        'lemuel': ['lemuel', 'lem'],
        'fredericka': ['fredericka', 'freddy', 'ricka', 'freda', 'frieda'],
        'sion': ['simon', 'si', 'sion'],
        'dickon': ['richard', 'dick', 'dickon', 'dickie', 'dicky', 'rick', 'rich', 'ricky'],
        'donny': ['donny', 'donald'],
        'aldrich': ['aldrich', 'riche', 'rich'],
        'cintha': ['cynthia', 'cintha', 'cindy'],
        'donald': ['donny', 'donald'],
        'jimmie': ['jim', 'jimmie'],
        'ursula': ['ursula', 'sulie', 'sula'],
        'hodge': ['roger', 'roge', 'bobby', 'hodge', 'rod', 'robby', 'rupert', 'robin'],
        'grissel': ['griselda', 'grissel'],
        'debra': ['debra', 'deb', 'debbie'],
        'bige': ['abijah', 'ab', 'bige'],
        'lorraine': ['lorraine', 'lorrie'],
        'veda': ['laveda', 'veda'],
        'levone': ['levone', 'von'],
        'anne': ['anne', 'annie', 'nana', 'ann', 'nan', 'nanny', 'nancy'],
        'peg': ['peg', 'peggy'],
        'anna': ['savannah', 'vannie', 'anna'],
        'columbus': ['columbus', 'clum'],
        'cora': ['corinne', 'cora', 'ora'],
        'sadie': ['sarah', 'sally', 'sadie'],
        'lucille': ['lucille', 'cille', 'lu', 'lucy', 'lou'],
        'bo': ['boetius', 'bo'],
        'nelle': ['nelle', 'nelly'],
        'burt': ['egbert', 'bert', 'burt'],
        'alexandra': ['alexandra', 'alex', 'sandy', 'alla', 'sandra'],
        'carol': ['caroline', 'lynn', 'carol', 'carrie', 'cassie', 'carole'],
        'victoria': ['victoria', 'torie', 'vic', 'vicki', 'tory', 'vicky'],
        'athy': ['eighta', 'athy'],
        'seph': ['persephone', 'seph', 'sephy'],
        'faith': ['faith', 'fay'],
        'algy': ['algernon', 'algy'],
        'stephie': ['stephanie', 'stephen', 'stephie', 'annie', 'steph'],
        'dotty': ['dotha', 'dotty'],
        'stuart': ['stuart', 'stu'],
        'fel': ['felicia', 'fel', 'felix', 'feli'],
        'silence': ['silence', 'liley'],
        'rollo': ['roland', 'rollo', 'lanny', 'orlando', 'rolly'],
        'jimmy': ['james', 'jimmy', 'jim', 'jamie', 'jimmie', 'jem'],
        'nerva': ['manerva', 'minerva', 'nervie', 'eve', 'nerva'],
        'ola': ['viola', 'ola', 'vi'],
        'tiff': ['tiffany', 'tiff', 'tiffy'],
        'kissy': ['calista', 'kissy'],
        'nadine': ['nadine', 'nada', 'deedee'],
        'elvira': ['elvira', 'elvie'],
        'lois': ['louise', 'eliza', 'lou', 'lois'],
        'ebbie': ['ebenezer', 'ebbie', 'eben', 'eb'],
        'pink': ['pinckney', 'pink'],
        'frannie': ['francine', 'franniey', 'fran', 'frannie', 'francie'],
        'abel': ['abel', 'ebbie', 'ab', 'abe', 'eb'],
        'beedy': ['obedience', 'obed', 'beda', 'beedy', 'biddie'],
        'manoah': ['manoah', 'noah'],
        'sonny': ['judson', 'sonny', 'jud'],
        'jo': ['josephine', 'fina', 'jody', 'jo', 'josey', 'joey'],
        'kathleen': ['kathleen', 'kathy', 'katy', 'lena', 'kittie', 'kit', 'trina', 'cathy', 'kay', 'cassie'],
        'anderson': ['anderson', 'andy'],
        'joseph': ['joseph', 'jody', 'jos', 'joe', 'joey'],
        'chauncey': ['chauncey', 'chan'],
        'lunetta': ['lunetta', 'nettie'],
        'aurelia': ['aurelia', 'ree', 'rilly', 'orilla', 'aurilla', 'ora'],
        'immanuel': ['immanuel', 'manuel', 'emmanuel'],
        'jane': ['virginia', 'jane', 'jennie', 'ginny', 'virgy', 'ginger'],
        'erasmus': ['erasmus', 'raze', 'rasmus'],
        'maria': ['marietta', 'mariah', 'mercy', 'polly', 'may', 'molly', 'mitzi', 'minnie', 'mollie', 'mae', 'maureen',
                  'marion', 'marie', 'mamie', 'mary', 'maria'],
        'sinah': ['lucina', 'sinah'],
        'happy': ['karonhappuck', 'karon', 'karen', 'carrie', 'happy'],
        'bradford': ['bradford', 'ford', 'brad'],
        'cass': ['caswell', 'cass'],
        'elenor': ['leonore', 'nora', 'honor', 'elenor'],
        'kenzy': ['mackenzie', 'kenzy', 'mac', 'mack'],
        'middie': ['araminta', 'armida', 'middie', 'ruminta', 'minty'],
        'keziah': ['keziah', 'kizza', 'kizzie'],
        'ford': ['clifford', 'ford', 'cliff'],
        'melanie': ['melanie', 'mellie'],
        'larry': ['lawrence', 'lorry', 'larry', 'lon', 'lonny', 'lorne'],
        'lydia': ['lydia', 'lyddy'],
        'jennifer': ['jenny', 'jennifer'],
        'lottie': ['lotta', 'lottie'],
        'junior': ['junior', 'junie', 'june', 'jr'],
        'lina': ['paulina', 'polly', 'lina'],
        'josiah': ['josiah', 'jos'],
        'fay': ['faith', 'fay'],
        'provy': ['providence', 'provy'],
        'emil': ['emil', 'emily'],
        'clifton': ['clifton', 'tony', 'cliff'],
        'rhyna': ['rhyna', 'rhynie'],
        'aze': ['azariah', 'riah', 'aze'],
        'tommy': ['tommy', 'thomas'],
        'crystal': ['crystal', 'chris', 'tal', 'stal', 'crys'],
        'sigismund': ['sigismund', 'sig'],
        'wilhelmina': ['wilhelmina', 'mina', 'wilma', 'willie', 'minnie'],
        'nervie': ['manerva', 'minerva', 'nervie', 'eve', 'nerva'],
        'aquilla': ['aquilla', 'quil', 'quillie'],
        'curt': ['curtis', 'curt'],
        'phil': ['phillip', 'phil'],
        'hobkin': ['robert', 'hob', 'hobkin', 'dob', 'rob', 'bobby', 'dobbin', 'bob'],
        'chesley': ['chesley', 'chet'],
        'vonnie': ['veronica', 'vonnie', 'ron', 'ronna', 'ronie', 'frony', 'franky', 'ronnie'],
        'frederick': ['frederick', 'freddie', 'freddy', 'fritz', 'fred'],
        'maggie': ['margarita', 'maggie', 'meg', 'metta', 'midge', 'greta', 'megan', 'maisie', 'madge', 'marge',
                   'daisy', 'peggie', 'rita', 'margo'],
        'chan': ['chauncey', 'chan'],
        'ezekiel': ['ezekiel', 'zeke', 'ez'],
        'char': ['charlotte', 'char', 'sherry', 'lottie', 'lotta'],
        'curg': ['lecurgus', 'curg'],
        'trix': ['trix', 'trixie'],
        'chat': ['charity', 'chat'],
        'flossy': ['florence', 'flossy', 'flora', 'flo'],
        'cassie': ['kathleen', 'kathy', 'katy', 'lena', 'kittie', 'kit', 'trina', 'cathy', 'kay', 'cassie'],
        'adelaide': ['della', 'adela', 'delilah', 'adelaide'],
        'ansel': ['anselm', 'ansel', 'selma', 'anse', 'ance'],
        'norby': ['norbert', 'bert', 'norby'],
        'ramona': ['ramona', 'mona'],
        'theotha': ['theotha', 'otha'],
        'lazar': ['eleazer', 'lazar'],
        'alastair': ['alastair', 'al'],
        'nan': ['nancy', 'ann', 'nan', 'nanny'],
        'nick': ['nik', 'nick'],
        'nap': ['napoleon', 'nap', 'nappy', 'leon'],
        'ellen': ['lena', 'ellen'],
        'nat': ['nathaniel', 'than', 'nathan', 'nate', 'nat', 'natty'],
        'rolf': ['rudolphus', 'dolph', 'rudy', 'olph', 'rolf'],
        'naz': ['ignatzio', 'naz', 'iggy', 'nace'],
        'richie': ['richie', 'richard'],
        'mock': ['democrates', 'mock'],
        'tess': ['theresa', 'tessie', 'thirza', 'tessa', 'terry', 'tracy', 'tess', 'thursa'],
        'lena': ['magdelina', 'lena', 'magda', 'madge'],
        'jettie': ['josetta', 'jettie'],
        'mervin': ['merv', 'mervin'],
        'lucia': ['lucia', 'lucy', 'lucius'],
        'jedidiah': ['jedidiah', 'jed'],
        'evan': ['evangeline', 'ev', 'evan', 'vangie'],
        'maureen': ['maureen', 'mary'],
        'miranda': ['miranda', 'randy', 'mandy', 'mira'],
        'epaphroditius': ['epaphroditius', 'dite', 'ditus', 'eppa', 'dyche', 'dyce'],
        'crissy': ['kristine', 'kris', 'kristy', 'tina', 'christy', 'chris', 'crissy'],
        'ariadne': ['ariadne', 'arie'],
        'loren': ['lorenzo', 'loren'],
        'beda': ['obedience', 'obed', 'beda', 'beedy', 'biddie'],
        'geraldine': ['jerry', 'jereme', 'geraldine'],
        'fronia': ['sophronia', 'frona', 'sophia', 'fronia'],
        'justus': ['justin', 'justus', 'justina'],
        'constance': ['constance', 'connie'],
        'cathleen': ['cathy', 'kathy', 'cathleen', 'catherine'],
        'tamzine': ['thomasa', 'tamzine'],
        'socrates': ['socrates', 'crate'],
        'lafayette': ['lafayette', 'laffie', 'fate'],
        'doda': ['dorothea', 'doda', 'dora'],
        'vicy': ['levicy', 'vicy'],
        'willis': ['willis', 'willy', 'bill'],
        'katy': ['katy', 'kathy'],
        'ron': ['veronica', 'vonnie', 'ron', 'ronna', 'ronie', 'frony', 'franky', 'ronnie'],
        'philetus': ['philetus', 'leet', 'phil'],
        'rob': ['robert', 'hob', 'hobkin', 'dob', 'rob', 'bobby', 'dobbin', 'bob'],
        'bridie': ['bridget', 'bridie', 'biddy', 'bridgie', 'biddie'],
        'rod': ['roger', 'roge', 'bobby', 'hodge', 'rod', 'robby', 'rupert', 'robin'],
        'morey': ['seymour', 'see', 'morey'],
        'laura': ['laurinda', 'laura', 'lawrence'],
        'roy': ['leroy', 'roy', 'lee', 'l.r.'],
        'roz': ['roz', 'rosalyn'],
        'vinnie': ['vincenzo', 'vic', 'vinnie', 'vin', 'vinny'],
        'marion': ['marion', 'mary'],
        'delbert': ['delbert', 'bert', 'del'],
        'izzy': ['isidore', 'izzy'],
        'dalton': ['dalton', 'dahl'],
        'levicy': ['levicy', 'vicy'],
        'kate': ['katherine', 'kathy', 'katy', 'lena', 'kittie', 'kaye', 'kit', 'trina', 'cathy', 'kay', 'kate',
                 'cassie'],
        'vet': ['sylvester', 'sy', 'sly', 'vet', 'syl', 'vester', 'si', 'vessie'],
        'simon': ['simon', 'si', 'sion'],
        'marissa': ['marissa', 'rissa'],
        'algernon': ['algernon', 'algy'],
        'pocahontas': ['pocahontas', 'pokey'],
        'junie': ['junior', 'junie', 'june', 'jr'],
        'allisandra': ['allisandra', 'allie'],
        'georgiana': ['georgia', 'george', 'georgiana'],
        'arie': ['arielle', 'arie'],
        'middy': ['maud', 'middy'],
        'celia': ['celeste', 'lessie', 'celia'],
        'lilly': ['lilly', 'lily'],
        'rella': ['cinderella', 'arilla', 'rella', 'cindy', 'rilla'],
        'charles': ['charlie', 'charles', 'chuck'],
        'eloise': ['heloise', 'lois', 'eloise', 'elouise'],
        'irvin': ['irvin', 'irving'],
        'hannah': ['susannah', 'hannah', 'susie', 'sue', 'sukey'],
        'scotty': ['scott', 'scotty', 'sceeter', 'squat', 'scottie'],
        'gina': ['regina', 'reggie', 'gina'],
        'prudence': ['prudy', 'prudence'],
        'delphia': ['philly', 'delphia'],
        'kizza': ['keziah', 'kizza', 'kizzie'],
        'felicity': ['felicity', 'flick', 'tick'],
        'mantha': ['samantha', 'sammy', 'sam', 'mantha'],
        'darry': ['darlene', 'lena', 'darry'],
        'clement': ['clementine', 'clement', 'clem'],
        'bryant': ['brian', 'bryan', 'bryant'],
        'margarita': ['margarita', 'maggie', 'meg', 'metta', 'midge', 'greta', 'megan', 'maisie', 'madge', 'marge',
                      'daisy', 'peggie', 'rita', 'margo'],
        'henrietta': ['henrietta', 'hank', 'etta', 'etty', 'retta', 'nettie'],
        'arabelle': ['arabelle', 'ara', 'bella', 'arry', 'belle'],
        'eva': ['evaline', 'eva', 'lena', 'eve'],
        'louie': ['louis', 'lewis', 'louise', 'louie', 'lou'],
        'michael': ['mike', 'micky', 'mick', 'michael'],
        'eve': ['manerva', 'minerva', 'nervie', 'eve', 'nerva'],
        'minnie': ['wilhelmina', 'mina', 'wilma', 'willie', 'minnie'],
        'gretta': ['margaretta', 'maggie', 'meg', 'peg', 'midge', 'margie', 'madge', 'peggy', 'marge', 'daisy',
                   'margery', 'gretta', 'rita'],
        'gus': ['gustavus', 'gus'],
        'asenath': ['asenath', 'sene', 'assene', 'natty'],
        'ignatzio': ['ignatzio', 'naz', 'iggy', 'nace'],
        'barbara': ['barbie', 'barbara'],
        'bernie': ['berney', 'bernie'],
        'claudia': ['claudia', 'claud'],
        'ezra': ['ezra', 'ez'],
        'syphorous': ['onicyphorous', 'cyphorus', 'osaforus', 'syphorous', 'one', 'cy', 'osaforum'],
        'delius': ['delia', 'fidelia', 'cordelia', 'delius'],
        'samyra': ['samyra', 'myra'],
        'honora': ['honora', 'honey', 'nora', 'norry', 'norah'],
        'fina': ['josephine', 'fina', 'jody', 'jo', 'josey', 'joey'],
        'sulie': ['ursula', 'sulie', 'sula'],
        'lanson': ['alanson', 'al', 'lanson'],
        'naomi': ['naomi', 'omi'],
        'colie': ['cole', 'colie'],
        'alfy': ['alfreda', 'freddy', 'alfy', 'freda', 'frieda'],
        'elisa': ['elisa', 'lisa'],
        'junius': ['june', 'junius'],
        'victor': ['victor', 'vic'],
        'roxanne': ['roxanne', 'roxie', 'rose', 'ann'],
        'theodore': ['theodore', 'theo', 'ted', 'teddy'],
        'barbie': ['barbie', 'barbara'],
        'mollie': ['marietta', 'mariah', 'mercy', 'polly', 'may', 'molly', 'mitzi', 'minnie', 'mollie', 'mae',
                   'maureen', 'marion', 'marie', 'mamie', 'mary', 'maria'],
        'eliza': ['louise', 'eliza', 'lou', 'lois'],
        'tessie': ['theresa', 'tessie', 'thirza', 'tessa', 'terry', 'tracy', 'tess', 'thursa'],
        'addy': ['adelphia', 'philly', 'delphia', 'adele', 'dell', 'addy'],
        'ophi': ['theophilus', 'ophi'],
        'laurence': ['laurence', 'lorry', 'larry', 'lon', 'lonny', 'lorne'],
        'nicholas': ['nickie', 'nicholas'],
        'ginny': ['virginia', 'jane', 'jennie', 'ginny', 'virgy', 'ginger'],
        'lolly': ['lillian', 'lil', 'lilly', 'lolly'],
        'l.b.': ['littleberry', 'little', 'berry', 'l.b.'],
        'littleberry': ['littleberry', 'little', 'berry', 'l.b.'],
        'lea': ['leanne', 'lea', 'annie'],
        'angelina': ['angelina', 'lina'],
        'flo': ['florence', 'flossy', 'flora', 'flo'],
        'aline': ['aline', 'adeline'],
        'angeline': ['angela', 'angelica', 'angelina', 'angel', 'angeline', 'jane', 'angie'],
        'henry': ['henry', 'hank', 'hal', 'harry'],
        'lem': ['lemuel', 'lem'],
        'len': ['leonard', 'lineau', 'leo', 'leon', 'len', 'lenny'],
        'leo': ['leonard', 'lineau', 'leo', 'leon', 'len', 'lenny'],
        'peggy': ['peg', 'peggy'],
        'les': ['lester', 'les'],
        'ernest': ['ernestine', 'teeny', 'ernest', 'tina', 'erna'],
        'elsey': ['elze', 'elsey'],
        'posthuma': ['posthuma', 'humey'],
        'micah': ['michael', 'micky', 'mike', 'micah', 'mick'],
        'demerias': ['demerias', 'dea', 'maris', 'mary'],
        'virgy': ['virginia', 'jane', 'jennie', 'ginny', 'virgy', 'ginger'],
        'nelly': ['nelle', 'nelly'],
        'jay': ['jayme', 'jay'],
        'calvin': ['calvin', 'vin', 'vinny', 'cal'],
        'alyssa': ['alyssa', 'lissia', 'al', 'ally'],
        'franklin': ['franklin', 'fran', 'frank'],
        'orphelia': ['orphelia', 'phelia'],
        'bob': ['robert', 'hob', 'hobkin', 'dob', 'rob', 'bobby', 'dobbin', 'bob'],
        'gene': ['eugene', 'gene'],
        'aggy': ['augustina', 'tina', 'aggy', 'gatsy', 'gussie'],
        'honor': ['leonore', 'nora', 'honor', 'elenor'],
        'doris': ['doris', 'dora'],
        'phena': ['tryphena', 'phena'],
        'sheila': ['sheila', 'cecilia'],
        'hopp': ['hopkins', 'hopp', 'hop'],
        'clare': ['clarence', 'clare', 'clair'],
        'win': ['winfield', 'field', 'winny', 'win'],
        'app': ['absalom', 'app', 'ab', 'abbie'],
        'clara': ['clarissa', 'cissy', 'clara'],
        'dennison': ['dennison', 'denny'],
        'kristine': ['kristine', 'kris', 'kristy', 'tina', 'christy', 'chris', 'crissy'],
        'manny': ['manuel', 'emanuel', 'manny'],
        'mckenna': ['mckenna', 'ken', 'kenna', 'meaka'],
        'winnie': ['winnifred', 'freddie', 'freddy', 'winny', 'winnie', 'fred'],
        'lurana': ['lurana', 'lura'],
        'jan': ['janice', 'jan'],
        'russell': ['rusty', 'russell'],
        'elijah': ['elijah', 'lige', 'eli'],
        'magdelina': ['magdelina', 'lena', 'magda', 'madge'],
        'mittie': ['mitzie', 'mittie', 'mitty'],
        'angela': ['angela', 'angelica', 'angelina', 'angel', 'angeline', 'jane', 'angie'],
        'rissa': ['marissa', 'rissa'],
        'inez': ['inez', 'agnes'],
        'indie': ['india', 'indie', 'indy'],
        'roxanna': ['roxanna', 'roxie', 'rose', 'ann'],
        'andy': ['andy', 'andrew', 'drew'],
        'debbie': ['debra', 'deb', 'debbie'],
        'emeline': ['emeline', 'em', 'emmy', 'emma', 'milly', 'emily'],
        'malc': ['malcolm', 'mac', 'mal', 'malc'],
        'tabitha': ['tabitha', 'tabby'],
        'abijah': ['abijah', 'ab', 'bige'],
        'jonathan': ['jonathan', 'john', 'nathan'],
        'reynold': ['reynold', 'reginald'],
        'pres': ['prescott', 'scotty', 'scott', 'pres'],
        'rick': ['rick', 'ricky'],
        'hezekiah': ['hezekiah', 'hy', 'hez', 'kiah'],
        'eliphalel': ['eliphalel', 'life'],
        'clum': ['columbus', 'clum'],
        'india': ['india', 'indie', 'indy'],
        'katelyn': ['katelyn', 'kay', 'kate', 'kaye'],
        'penie': ['philipina', 'phoebe', 'penie'],
        'casey': ['casey', 'k.c.'],
        'felty': ['valentine', 'felty'],
        'babs': ['barbara', 'barby', 'babs', 'bab', 'bobbie'],
        'onnie': ['iona', 'onnie'],
        'connie': ['constance', 'connie'],
        'olive': ['olive', 'nollie', 'livia', 'ollie'],
        'amelia': ['parmelia', 'amelia', 'milly', 'melia'],
        'claud': ['claudia', 'claud'],
        'eliphalet': ['eliphalet', 'left'],
        'charity': ['charity', 'chat'],
        'judi': ['judith', 'judie', 'juda', 'judy', 'judi', 'jude'],
        'malinda': ['malinda', 'lindy'],
        'gabriel': ['gabriel', 'gabe', 'gabby'],
        'juda': ['judith', 'judie', 'juda', 'judy', 'judi', 'jude'],
        'abednego': ['abednego', 'bedney'],
        'jude': ['judith', 'judie', 'juda', 'judy', 'judi', 'jude'],
        'erwin': ['irwin', 'erwin'],
        'judy': ['judy', 'judith'],
        'evangeline': ['evangeline', 'ev', 'evan', 'vangie'],
        'luella': ['luella', 'lula', 'ella', 'lu'],
        'cam': ['campbell', 'cam'],
        'cal': ['calvin', 'vin', 'vinny', 'cal'],
        'margery': ['marge', 'margery', 'margaret', 'margaretta'],
        'webster': ['webster', 'webb'],
        'mees': ['bartholomew', 'bartel', 'bat', 'meus', 'bart', 'mees'],
        'natasha': ['natasha', 'tasha', 'nat'],
        'lessie': ['celeste', 'lessie', 'celia'],
        'kenny': ['kent', 'ken', 'kenny', 'kendrick'],
        'kenneth': ['kenny', 'ken', 'kenneth'],
        'biddy': ['bridget', 'bridie', 'biddy', 'bridgie', 'biddie'],
        'edna': ['edna', 'edny'],
        'etta': ['loretta', 'etta', 'lorrie', 'retta'],
        'edny': ['edna', 'edny'],
        'etty': ['henrietta', 'hank', 'etta', 'etty', 'retta', 'nettie'],
        'vallie': ['valentina', 'felty', 'vallie', 'val'],
        'gabby': ['gabrielle', 'ella', 'gabby'],
        'lenora': ['lenora', 'nora', 'lee'],
        'tal': ['crystal', 'chris', 'tal', 'stal', 'crys'],
        'bessie': ['elizabeth', 'libby', 'lisa', 'lib', 'lizzie', 'eliza', 'betsy', 'liza', 'betty', 'bessie', 'bess',
                   'beth', 'liz'],
        'arnie': ['arnold', 'arnie'],
        'dennis': ['dennis', 'denny'],
        'alverta': ['alverta', 'virdie', 'vert'],
        'jincy': ['jincy', 'jane'],
        'clair': ['clarence', 'clare', 'clair'],
        'biddie': ['obedience', 'obed', 'beda', 'beedy', 'biddie'],
        'sis': ['frances', 'sis', 'cissy', 'frankie', 'franniey', 'fran', 'francie', 'frannie', 'fanny'],
        'sidney': ['sidney', 'syd', 'sid'],
        'dicie': ['dicey', 'dicie'],
        'kenna': ['mckenna', 'ken', 'kenna', 'meaka'],
        'di': ['diane', 'dicey', 'didi', 'di'],
        'frieda': ['frieda', 'freddie', 'freddy', 'fred'],
        'camille': ['camille', 'millie', 'cammie'],
        'brian': ['brian', 'bryan', 'bryant'],
        'sig': ['sigismund', 'sig'],
        'dosie': ['eudoris', 'dossie', 'dosie'],
        'hipsie': ['hepsibah', 'hipsie'],
        'sid': ['sydney', 'sid'],
        'cyrenius': ['cyrenius', 'swene', 'cy', 'serene', 'renius', 'cene'],
        'ferdinand': ['ferdinand', 'freddie', 'freddy', 'ferdie', 'fred'],
        'pheriba': ['pheriba', 'pherbia', 'ferbie'],
        'phelia': ['orphelia', 'phelia'],
        'monna': ['monica', 'monna', 'monnie'],
        'levy': ['aleva', 'levy', 'leve'],
        'samuel': ['samuel', 'sammy', 'sam'],
        'mat': ['mat', 'mattie'],
        'tryphena': ['tryphena', 'phena'],
        'may': ['may', 'mae'],
        'fran': ['franklin', 'fran', 'frank'],
        'gerhardt': ['gerhardt', 'gay'],
        'rupert': ['roger', 'roge', 'bobby', 'hodge', 'rod', 'robby', 'rupert', 'robin'],
        'ronald': ['ronny', 'ronald'],
        'bertie': ['roberta', 'robbie', 'bert', 'bobbie', 'birdie', 'bertie'],
        'mac': ['malcolm', 'mac', 'mal', 'malc'],
        'mae': ['may', 'mae'],
        'iggy': ['ignatzio', 'naz', 'iggy', 'nace'],
        'mal': ['malcolm', 'mac', 'mal', 'malc'],
        'leve': ['aleva', 'levy', 'leve'],
        'pandora': ['pandora', 'dora'],
        'rilly': ['orilla', 'rilly', 'ora'],
        'sy': ['sylvester', 'sy', 'sly', 'vet', 'syl', 'vester', 'si', 'vessie'],
        'adelphia': ['adelphia', 'philly', 'delphia', 'adele', 'dell', 'addy'],
        'lucinda': ['lucy', 'lucinda'],
        'rudolphus': ['rudolphus', 'dolph', 'rudy', 'olph', 'rolf'],
        'kiah': ['hezekiah', 'hy', 'hez', 'kiah'],
        'irwin': ['irwin', 'erwin'],
        'obediah': ['obie', 'obediah'],
        'emanuel': ['manuel', 'emanuel', 'manny'],
        'hepsibah': ['hepsibah', 'hipsie'],
        'claire': ['claire', 'clair', 'clare', 'clara'],
        'permelia': ['permelia', 'melly', 'milly', 'mellie'],
        'laurie': ['lauryn', 'laurie'],
        'martina': ['martina', 'tina'],
        'nancy': ['nancy', 'ann', 'nan', 'nanny'],
        'laffie': ['lafayette', 'laffie', 'fate'],
        'issy': ['isadora', 'issy', 'dora'],
        'steve': ['steven', 'steve', 'steph'],
        'tammy': ['tamarra', 'tammy'],
        'clarissa': ['clarissa', 'cissy', 'clara'],
        'billiewilhelm': ['wilma', 'william', 'billiewilhelm'],
        'marguerite': ['marguerite', 'peggy'],
        'kristen': ['kristen', 'chris'],
        'josephine': ['pheney', 'josephine'],
        'peregrine': ['peregrine', 'perry'],
        'susannah': ['susannah', 'hannah', 'susie', 'sue', 'sukey'],
        'philinda': ['philinda', 'linda', 'lynn', 'lindy'],
        'joanne': ['joanne', 'jo'],
        'joanna': ['joanna', 'hannah', 'jody', 'jo', 'joan'],
        'serilla': ['serilla', 'rilla'],
        'tavia': ['octavia', 'tave', 'tavia'],
        'cornelius': ['cornelius', 'conny', 'niel', 'corny', 'con'],
        'irene': ['irene', 'rena'],
        'franklind': ['franklind', 'frank'],
        'jock': ['john', 'jack', 'johnny', 'jock'],
        'felicia': ['felicia', 'fel', 'felix', 'feli'],
        'otis': ['otis', 'ode', 'ote'],
        'bridget': ['bridget', 'bridie', 'biddy', 'bridgie', 'biddie'],
        'dosia': ['theodosia', 'theo', 'dosia', 'theodosius'],
        'jim': ['jim', 'jimmie'],
        'laveda': ['laveda', 'veda'],
        'amabel': ['mabel', 'mehitabel', 'amabel'],
        'lu': ['luella', 'lula', 'ella', 'lu'],
        'kizzie': ['keziah', 'kizza', 'kizzie'],
        'jody': ['josephine', 'fina', 'jody', 'jo', 'josey', 'joey'],
        'alexander': ['alexandria', 'drina', 'alexander', 'alla', 'sandra'],
        'tory': ['victoria', 'torie', 'vic', 'vicki', 'tory', 'vicky'],
        'wen': ['wendy', 'wen'],
        'carole': ['caroline', 'lynn', 'carol', 'carrie', 'cassie', 'carole'],
        'nettie': ['pernetta', 'nettie'],
        'winifred': ['winifred', 'freddie', 'winnie', 'winnet'],
        'cyphorus': ['onicyphorous', 'cyphorus', 'osaforus', 'syphorous', 'one', 'cy', 'osaforum'],
        'dal': ['dal', 'dahl'],
        'swene': ['cyrenius', 'swene', 'cy', 'serene', 'renius', 'cene'],
        'dan': ['sheridan', 'dan', 'danny', 'sher'],
        'metta': ['margarita', 'maggie', 'meg', 'metta', 'midge', 'greta', 'megan', 'maisie', 'madge', 'marge', 'daisy',
                  'peggie', 'rita', 'margo'],
        'edmond': ['edmond', 'ed', 'eddie', 'eddy'],
        'sarilla': ['sarilla', 'silla'],
        'hamilton': ['hamilton', 'ham'],
        'frony': ['veronica', 'vonnie', 'ron', 'ronna', 'ronie', 'frony', 'franky', 'ronnie'],
        'terence': ['terry', 'terence'],
        'cage': ['micajah', 'cage'],
        'day': ['david', 'dave', 'day', 'davey'],
        'wilda': ['wilda', 'willie'],
        'cory': ['cory', 'coco', 'cordy', 'ree'],
        'tish': ['letitia', 'tish', 'titia', 'lettice', 'lettie'],
        'james': ['jamie', 'james'],
        'anse': ['anselm', 'ansel', 'selma', 'anse', 'ance'],
        'brody': ['broderick', 'ricky', 'brody', 'brady', 'rick'],
        'didi': ['diane', 'dicey', 'didi', 'di'],
        'carlton': ['carlton', 'carl'],
        'billy': ['william', 'willy', 'bell', 'bela', 'bill', 'will', 'billy', 'willie'],
        'melchizedek': ['melchizedek', 'zadock', 'dick'],
        'betty': ['elizabeth', 'libby', 'lisa', 'lib', 'lizzie', 'eliza', 'betsy', 'liza', 'betty', 'bessie', 'bess',
                  'beth', 'liz'],
        'stacia': ['eustacia', 'stacia', 'stacy'],
        'edie': ['edythe', 'edie', 'edye'],
        'gerrie': ['gerrie', 'geraldine'],
        'sophronia': ['sophronia', 'frona', 'sophia', 'fronia'],
        'em': ['emeline', 'em', 'emmy', 'emma', 'milly', 'emily'],
        'adeline': ['aline', 'adeline'],
        'cyrus': ['cyrus', 'cy'],
        'calliedona': ['caldonia', 'calliedona'],
        'ed': ['edwin', 'ed', 'eddie', 'win', 'eddy', 'ned'],
        'quillie': ['aquilla', 'quil', 'quillie'],
        'rolly': ['roland', 'rollo', 'lanny', 'orlando', 'rolly'],
        'eb': ['ebenezer', 'ebbie', 'eben', 'eb'],
        'ez': ['ezra', 'ez'],
        'virdie': ['alverta', 'virdie', 'vert'],
        'ev': ['evelyn', 'evelina', 'ev', 'eve'],
        'sandy': ['sanford', 'sandy'],
        'theodosius': ['theodosia', 'theo', 'dosia', 'theodosius'],
        'dorothea': ['dorothea', 'doda', 'dora'],
        'matt': ['matthias', 'thys', 'matt', 'thias'],
        'jackson': ['jackson', 'jack'],
        'sha': ['sharon', 'sha', 'shay'],
        'kenj': ['kendra', 'kenj', 'kenji', 'kay', 'kenny'],
        'rose': ['roxanne', 'roxie', 'rose', 'ann'],
        'ricky': ['ricky', 'dick', 'rich'],
        'bethena': ['bethena', 'beth', 'thaney'],
        'alison': ['alison', 'ali'],
        'kent': ['kent', 'ken', 'kenny', 'kendrick'],
        'ricka': ['fredericka', 'freddy', 'ricka', 'freda', 'frieda'],
        'rea': ['andrea', 'drea', 'rea', 'andrew'],
        'elminie': ['elminie', 'minnie'],
        'reg': ['reginald', 'reggie', 'naldo', 'reg', 'renny'],
        'ree': ['cory', 'coco', 'cordy', 'ree'],
        'nikki': ['nicole', 'nole', 'nikki', 'cole'],
        'calpurnia': ['calpurnia', 'cally'],
        'ples': ['pleasant', 'ples'],
        'jessica': ['jessica', 'jessie'],
        'frank': ['franklind', 'frank'],
        'molly': ['mary', 'mamie', 'molly', 'mae', 'polly', 'mitzi'],
        'hiram': ['hiram', 'hy'],
        'mima': ['jemima', 'mima'],
        'jill': ['julia', 'julie', 'jill'],
        'california': ['california', 'callie'],
        'carl': ['charles', 'charlie', 'chuck', 'carl', 'chick'],
        'carm': ['carmon', 'charm', 'cammie', 'carm'],
        'mimi': ['miriam', 'mimi', 'mitzi', 'mitzie'],
        'philip': ['philip', 'phil'],
        'vandalia': ['vandalia', 'vannie'],
        'ora': ['orilla', 'rilly', 'ora'],
        'gussie': ['gus', 'gussie'],
        'isidore': ['isidore', 'izzy'],
        'democrates': ['democrates', 'mock'],
        'estella': ['estella', 'essy', 'stella'],
        'melly': ['permelia', 'melly', 'milly', 'mellie'],
        'estelle': ['estelle', 'essy', 'stella'],
        'horace': ['horace', 'horry'],
        'david': ['david', 'dave', 'day', 'davey'],
        'ryan': ['ryan', 'ry'],
        'archibald': ['archibald', 'archie'],
        'essie': ['esther', 'hester', 'essie'],
        'yul': ['yulan', 'lan', 'yul'],
        'adrian': ['adrienne', 'adrian'],
        'eighta': ['eighta', 'athy'],
        'loretta': ['loretta', 'etta', 'lorrie', 'retta'],
        'saul': ['solomon', 'sal', 'salmon', 'sol', 'solly', 'saul', 'zolly'],
        'austin': ['augustus', 'gus', 'austin', 'august'],
        'vester': ['sylvester', 'sy', 'sly', 'vet', 'syl', 'vester', 'si', 'vessie'],
        'kendall': ['kendall', 'ken', 'kenny'],
        'leonore': ['leonore', 'nora', 'honor', 'elenor'],
        'leonora': ['leonora', 'nora', 'nell', 'nellie'],
        'matthias': ['matthias', 'thys', 'matt', 'thias'],
        'tanafra': ['tanafra', 'tanny'],
        'ona': ['yeona', 'onie', 'ona'],
        'justina': ['justin', 'justus', 'justina'],
        'tobias': ['tobias', 'bias', 'toby'],
        'zay': ['isaiah', 'zadie', 'zay'],
        'temperance': ['temperance', 'tempy'],
        'franky': ['veronica', 'vonnie', 'ron', 'ronna', 'ronie', 'frony', 'franky', 'ronnie'],
        'george': ['georgia', 'george', 'georgiana'],
        'gertrude': ['trudy', 'gertrude'],
        'sharon': ['sharon', 'sha', 'shay'],
        'little': ['littleberry', 'little', 'berry', 'l.b.'],
        'ian': ['ian', 'john'],
        'clarence': ['clarence', 'clare', 'clair'],
        'stephan': ['stephan', 'steve'],
        'phenie': ['parthenia', 'teeny', 'parsuny', 'pasoonie', 'phenie'],
        'alfred': ['alfred', 'freddy', 'al', 'fred'],
        'missy': ['missy', 'melissa'],
        'nelia': ['cornelia', 'nelly', 'cornie', 'nelia', 'corny', 'nelle'],
        'nelson': ['nelson', 'nels'],
        'almira': ['almira', 'myra'],
        'natty': ['nathaniel', 'than', 'nathan', 'nate', 'nat', 'natty'],
        'abbie': ['absalom', 'app', 'ab', 'abbie'],
        'prissy': ['priscilla', 'prissy', 'cissy', 'cilla'],
        'frona': ['sophronia', 'frona', 'sophia', 'fronia'],
        'hub': ['hubert', 'bert', 'hugh', 'hub'],
        'seymour': ['seymour', 'see', 'morey'],
        'greta': ['margarita', 'maggie', 'meg', 'metta', 'midge', 'greta', 'megan', 'maisie', 'madge', 'marge', 'daisy',
                  'peggie', 'rita', 'margo'],
        'megan': ['megan', 'meg'],
        'alan': ['alan', 'al'],
        'antonia': ['antonia', 'tony', 'netta', 'ann'],
        'thad': ['thaddeus', 'thad'],
        'shirley': ['shirley', 'sherry', 'lee', 'shirl'],
        'than': ['nathaniel', 'than', 'nathan', 'nate', 'nat', 'natty'],
        'roberta': ['roberta', 'robbie', 'bert', 'bobbie', 'birdie', 'bertie'],
        'gil': ['gilbert', 'bert', 'gil', 'wilber'],
        'nathan': ['nathaniel', 'than', 'nathan', 'nate', 'nat', 'natty'],
        'bertram': ['bertram', 'bert'],
        'lissa': ['melissa', 'lisa', 'mel', 'missy', 'milly', 'lissa'],
        'bea': ['blanche', 'bea'],
        'see': ['seymour', 'see', 'morey'],
        'lucius': ['lucia', 'lucy', 'lucius'],
        'monteleon': ['monteleon', 'monte'],
        'tave': ['octavia', 'tave', 'tavia'],
        'reba': ['rebecca', 'beck', 'becca', 'reba', 'becky'],
        'sophie': ['sophia', 'sophie'],
        'bev': ['beverly', 'bev'],
        'sophia': ['sophronia', 'frona', 'sophia', 'fronia'],
        'delia': ['fidelia', 'delia'],
        'ana': ['anastasia', 'ana', 'stacy'],
        'chloe': ['chloe', 'clo'],
        'bert': ['wilber', 'will', 'bert'],
        'julian': ['julian', 'jule'],
        'ann': ['roxanne', 'roxie', 'rose', 'ann'],
        'clem': ['clementine', 'clement', 'clem'],
        'mavine': ['mavine', 'mave'],
        'nicey': ['vernisee', 'nicey'],
        'adela': ['della', 'adela', 'delilah', 'adelaide'],
        'bertha': ['bertha', 'bert', 'birdie', 'bertie'],
        'adele': ['adelphia', 'philly', 'delphia', 'adele', 'dell', 'addy'],
        'tessa': ['theresa', 'tessie', 'thirza', 'tessa', 'terry', 'tracy', 'tess', 'thursa'],
        'mitty': ['mitzie', 'mittie', 'mitty'],
        'allen': ['allen', 'al'],
        'absalom': ['absalom', 'app', 'ab', 'abbie'],
        'sula': ['ursula', 'sulie', 'sula'],
        'alfonse': ['alfonse', 'al'],
        'suki': ['suzanne', 'suki', 'sue', 'susie'],
        'janie': ['jane', 'janie', 'jessie', 'jean', 'jennie'],
        'angie': ['angela', 'angelica', 'angelina', 'angel', 'angeline', 'jane', 'angie'],
        'lila': ['delilah', 'lil', 'lila', 'dell', 'della'],
        'hoda': ['jahoda', 'hody', 'hodie', 'hoda'],
        'milly': ['permelia', 'melly', 'milly', 'mellie'],
        'martine': ['martine', 'tine'],
        'kristy': ['kristy', 'chris'],
        'octavia': ['octavia', 'tave', 'tavia'],
        'solly': ['solomon', 'sal', 'salmon', 'sol', 'solly', 'saul', 'zolly'],
        'montgomery': ['montgomery', 'monty', 'gum'],
        'jefferson': ['jefferson', 'sonny', 'jeff'],
        'sibbilla': ['sibbilla', 'sybill', 'sibbie', 'sibbell'],
        'linda': ['rosalyn', 'linda', 'roz', 'rosa', 'rose'],
        'martha': ['martha', 'marty', 'mattie', 'mat', 'patsy', 'patty'],
        'lily': ['lilly', 'lily'],
        'jaap': ['jacob', 'jaap', 'jake', 'jay'],
        'carthaette': ['carthaette', 'etta', 'etty'],
        'sol': ['solomon', 'sal', 'salmon', 'sol', 'solly', 'saul', 'zolly'],
        'hassie': ['haseltine', 'hassie'],
        'jorge': ['george', 'jorge', 'georgiana'],
        'armanda': ['armanda', 'mandy'],
        'woodrow': ['woodrow', 'woody', 'wood', 'drew'],
        'roxie': ['roxanne', 'roxie', 'rose', 'ann'],
        'simeon': ['simeon', 'si', 'sion'],
        'rilla': ['serilla', 'rilla'],
        'tracy': ['theresa', 'tessie', 'thirza', 'tessa', 'terry', 'tracy', 'tess', 'thursa'],
        'beth': ['elizabeth', 'libby', 'lisa', 'lib', 'lizzie', 'eliza', 'betsy', 'liza', 'betty', 'bessie', 'bess',
                 'beth', 'liz'],
        'sally': ['sarah', 'sally', 'sadie'],
        'herman': ['herman', 'harman', 'dutch'],
        'hob': ['robert', 'hob', 'hobkin', 'dob', 'rob', 'bobby', 'dobbin', 'bob'],
        'michelle': ['michelle', 'mickey'],
        'paddy': ['patrick', 'pate', 'peter', 'pat', 'patsy', 'paddy'],
        'frederica': ['frederica', 'frederick'],
        'lenny': ['leonard', 'lineau', 'leo', 'leon', 'len', 'lenny'],
        'bree': ['aubrey', 'bree'],
        'mur': ['muriel', 'mur'],
        'indy': ['india', 'indie', 'indy'],
        'ance': ['anselm', 'ansel', 'selma', 'anse', 'ance'],
        'link': ['lincoln', 'link'],
        'abraham': ['abraham', 'ab', 'abe'],
        'syl': ['sylvester', 'sy', 'sly', 'vet', 'syl', 'vester', 'si', 'vessie'],
        'boetius': ['boetius', 'bo'],
        'maxine': ['maxine', 'max'],
        'lorne': ['lawrence', 'lorry', 'larry', 'lon', 'lonny', 'lorne'],
        'brenda': ['brenda', 'brandy'],
        'eudoris': ['eudoris', 'dossie', 'dosie'],
        'egbert': ['egbert', 'bert', 'burt'],
        'niel': ['cornelius', 'conny', 'niel', 'corny', 'con'],
        'drusilla': ['drusilla', 'silla'],
        'audrey': ['audrey', 'dee'],
        'lloyd': ['floyd', 'lloyd'],
        'brina': ['sabrina', 'brina'],
        'dorothy': ['dorothy', 'dortha', 'dolly', 'dot', 'dotty'],
        'zeph': ['zephaniah', 'zeph'],
        'gert': ['gertrude', 'gertie', 'gert', 'trudy'],
        'arminda': ['arminda', 'mindie'],
        'ossy': ['waldo', 'ozzy', 'ossy'],
        'cicely': ['cicely', 'cilla'],
        'mehitabel': ['mehitabel', 'hetty', 'mitty', 'mabel', 'hitty'],
        'dick': ['ricky', 'dick', 'rich'],
        'mitzi': ['mitzi', 'mary', 'mittie', 'mitty'],
        'winnet': ['winifred', 'freddie', 'winnie', 'winnet'],
        'jap': ['jasper', 'jap', 'casper'],
        'barticus': ['barticus', 'bart'],
        'betsy': ['elizabeth', 'libby', 'lisa', 'lib', 'lizzie', 'eliza', 'betsy', 'liza', 'betty', 'bessie', 'bess',
                  'beth', 'liz'],
        'bernard': ['bernard', 'barney', 'bernie', 'berney'],
        'wood': ['woodrow', 'woody', 'wood', 'drew'],
        'lorenzo': ['lorenzo', 'loren'],
        'madeline': ['madie', 'madeline', 'madelyn'],
        'dicy': ['laodicia', 'dicy', 'cenia'],
        'caroline': ['chick', 'charlotte', 'caroline', 'chuck'],
        'demaris': ['demaris', 'dea', 'maris', 'mary'],
        'jacqueline': ['jacqueline', 'jackie', 'jack'],
        'winfield': ['winfield', 'field', 'winny', 'win'],
        'lynn': ['philinda', 'linda', 'lynn', 'lindy'],
        'silas': ['silas', 'si'],
        'nell': ['leonora', 'nora', 'nell', 'nellie'],
        'beatrice': ['beatrice', 'bea', 'trisha', 'trixie', 'trix'],
        'eppa': ['epaphroditius', 'dite', 'ditus', 'eppa', 'dyche', 'dyce'],
        'nels': ['nelson', 'nels'],
        'gee': ['jehu', 'hugh', 'gee'],
        'yvonne': ['yvonne', 'vonna'],
        'rodie': ['rhoda', 'rodie'],
        'ellswood': ['ellswood', 'elsey'],
        'jeannie': ['jeanne', 'jane', 'jeannie'],
        'abby': ['abigail', 'nabby', 'abby', 'gail'],
        'melvina': ['melvina', 'vina'],
        'menaalmena': ['philomena', 'menaalmena'],
        'carolann': ['carolann', 'carol', 'carole'],
        'hosey': ['hosea', 'hosey', 'hosie'],
        'hosea': ['hosea', 'hosey', 'hosie'],
        'mattie': ['matthew', 'thys', 'matt', 'thias', 'mattie', 'matty'],
        'roger': ['roger', 'roge', 'bobby', 'hodge', 'rod', 'robby', 'rupert', 'robin'],
        'claas': ['nicholas', 'nick', 'claes', 'claas'],
        'mercedes': ['mercedes', 'merci', 'sadie', 'mercy'],
        'netta': ['antonia', 'tony', 'netta', 'ann'],
        'madelyn': ['madie', 'madeline', 'madelyn'],
        'amanda': ['mandy', 'amanda'],
        'caswell': ['caswell', 'cass'],
        'samantha': ['samantha', 'sammy', 'sam', 'mantha'],
        'sukey': ['susannah', 'hannah', 'susie', 'sue', 'sukey'],
        'zachy': ['zachariah', 'zachy', 'zach', 'zeke'],
        'isabel': ['isabel', 'tibbie', 'bell', 'nib', 'belle', 'bella', 'nibby', 'ib', 'issy'],
        'rosie': ['roseanna', 'rose', 'ann', 'rosie', 'roz'],
        'salome': ['salome', 'loomie'],
        'zedediah': ['zedediah', 'dyer', 'zed', 'diah'],
        'august': ['augustus', 'gus', 'austin', 'august'],
        'freddy': ['winnifred', 'freddie', 'freddy', 'winny', 'winnie', 'fred'],
        'madison': ['madison', 'mattie', 'maddy'],
        'cole': ['nicole', 'nole', 'nikki', 'cole'],
        'ralph': ['raphael', 'ralph'],
        'teeny': ['parthenia', 'teeny', 'parsuny', 'pasoonie', 'phenie'],
        'marsha': ['marsha', 'marcie', 'mary'],
        'vanna': ['vanessa', 'essa', 'vanna', 'nessa'],
        'marvin': ['marvin', 'marv'],
        'nathaniel': ['nathaniel', 'than', 'nathan', 'nate', 'nat', 'natty'],
        'alzada': ['alzada', 'zada'],
        'ken': ['mckenna', 'ken', 'kenna', 'meaka'],
        'jos': ['josiah', 'jos'],
        'laurinda': ['laurinda', 'laura', 'lawrence'],
        'janet': ['jessie', 'jane', 'jess', 'janet'],
        'joy': ['joyce', 'joy'],
        'lettie': ['violetta', 'lettie'],
        'jr': ['junior', 'junie', 'june', 'jr'],
        'timmy': ['timothy', 'tim', 'timmy'],
        'zadock': ['melchizedek', 'zadock', 'dick'],
        'marietta': ['marietta', 'mariah', 'mercy', 'polly', 'may', 'molly', 'mitzi', 'minnie', 'mollie', 'mae',
                     'maureen', 'marion', 'marie', 'mamie', 'mary', 'maria'],
        'joe': ['joseph', 'jody', 'jos', 'joe', 'joey'],
        'belinda': ['belinda', 'belle', 'linda'],
        'cedric': ['cedric', 'ced', 'rick', 'ricky'],
        'robby': ['roger', 'roge', 'bobby', 'hodge', 'rod', 'robby', 'rupert', 'robin'],
        'jon': ['jon', 'john', 'nathan'],
        'marty': ['martin', 'marty'],
        'mindy': ['melinda', 'linda', 'mel', 'lynn', 'mindy', 'lindy'],
        'wallace': ['wallace', 'wally'],
        'norbert': ['norbert', 'bert', 'norby'],
        'adelbert': ['adelbert', 'del', 'albert', 'delbert', 'bert'],
        'matilda': ['matilda', 'tilly', 'maud', 'matty'],
        'maggy': ['margaret', 'maggie', 'meg', 'peg', 'midge', 'margy', 'margie', 'madge', 'peggy', 'maggy', 'marge',
                  'daisy', 'margery', 'gretta', 'rita'],
        'berry': ['littleberry', 'little', 'berry', 'l.b.'],
        'gerald': ['gerry', 'gerald', 'geraldine', 'jerry'],
        'zeke': ['zachariah', 'zachy', 'zach', 'zeke'],
        'duty': ['deuteronomy', 'duty'],
        'lecurgus': ['lecurgus', 'curg'],
        'malcolm': ['malcolm', 'mac', 'mal', 'malc'],
        'humey': ['posthuma', 'humey'],
        'denise': ['denise', 'dennis'],
        'zaddi': ['arzada', 'zaddi'],
        'cy': ['onicyphorous', 'cyphorus', 'osaforus', 'syphorous', 'one', 'cy', 'osaforum'],
        'rodger': ['rodger', 'roge', 'bobby', 'hodge', 'rod', 'robby', 'rupert', 'robin'],
        'prue': ['prudence', 'prue', 'prudy'],
        'manerva': ['manerva', 'minerva', 'nervie', 'eve', 'nerva'],
        'lorrie': ['lorraine', 'lorrie'],
        'heloise': ['heloise', 'lois', 'eloise', 'elouise'],
        'nicole': ['nicole', 'nole', 'nikki', 'cole'],
        'willy': ['wilson', 'will', 'willy', 'willie'],
        'oliver': ['ollie', 'oliver'],
        'lidia': ['lidia', 'lyddy'],
        'teddy': ['theodore', 'theo', 'ted', 'teddy'],
        'deuteronomy': ['deuteronomy', 'duty'],
        'alphus': ['alphinias', 'alphus'],
        'mark': ['marcus', 'mark'],
        'cordy': ['cory', 'coco', 'cordy', 'ree'],
        'marv': ['marvin', 'marv'],
        'rhoda': ['rhoda', 'rodie'],
        'quil': ['aquilla', 'quil', 'quillie'],
        'mary': ['mitzi', 'mary', 'mittie', 'mitty'],
        'edmund': ['edmund', 'ed', 'eddie', 'ted', 'eddy', 'ned'],
        'rube': ['rube', 'reuben'],
        'field': ['winfield', 'field', 'winny', 'win'],
        'mike': ['mike', 'micky', 'mick', 'michael'],
        'kingston': ['kingston', 'king'],
        'osaforum': ['onicyphorous', 'cyphorus', 'osaforus', 'syphorous', 'one', 'cy', 'osaforum'],
        'aubrey': ['aubrey', 'bree'],
        'eduardo': ['eduardo', 'ed', 'eddie', 'eddy'],
        'vince': ['vincent', 'vic', 'vince', 'vinnie', 'vin', 'vinny'],
        'georgia': ['georgia', 'george', 'georgiana'],
        'andrew': ['drew', 'andrew'],
        'meus': ['bartholomew', 'bartel', 'bat', 'meus', 'bart', 'mees'],
        'stephen': ['steve', 'stephen', 'steven'],
        'sigfired': ['sigfired', 'sid'],
        'andrea': ['andrea', 'drea', 'rea', 'andrew'],
        'elvie': ['elvira', 'elvie'],
        'napoleon': ['napoleon', 'nap', 'nappy', 'leon'],
        'wilbur': ['will', 'bill', 'willie', 'wilbur', 'fred'],
        'polly': ['pauline', 'polly'],
        'isabella': ['isabella', 'tibbie', 'nib', 'belle', 'bella', 'nibby', 'ib', 'issy'],
        'washington': ['washington', 'wash'],
        'isabelle': ['isabelle', 'tibbie', 'nib', 'belle', 'bella', 'nibby', 'ib', 'issy'],
        'osaforus': ['onicyphorous', 'cyphorus', 'osaforus', 'syphorous', 'one', 'cy', 'osaforum'],
        'mona': ['ramona', 'mona'],
        'arnold': ['arnold', 'arnie'],
        'augusta': ['augusta', 'tina', 'aggy', 'gatsy', 'gussie'],
        'will': ['wilson', 'will', 'willy', 'willie'],
        'vernisee': ['vernisee', 'nicey'],
        'hattie': ['harriet', 'hattie'],
        'riche': ['rich', 'dick', 'rick', 'riche', 'richard'],
        'margie': ['marjorie', 'margy', 'margie'],
        'abiel': ['abiel', 'ab'],
        'lanny': ['roland', 'rollo', 'lanny', 'orlando', 'rolly'],
        'jeanette': ['jeanette', 'jessie', 'jean', 'janet', 'nettie'],
        'vest': ['silvester', 'vester', 'si', 'sly', 'vest', 'syl'],
        'suzanne': ['suzanne', 'suki', 'sue', 'susie'],
        'iva': ['iva', 'ivy'],
        'evelyn': ['evelyn', 'evelina', 'ev', 'eve'],
        'candace': ['candace', 'candy', 'dacey'],
        'ellender': ['ellender', 'nellie', 'ellen', 'helen'],
        'bias': ['tobias', 'bias', 'toby'],
        'perry': ['peregrine', 'perry'],
        'lillah': ['lillah', 'lil', 'lilly', 'lily', 'lolly'],
        'ivy': ['iva', 'ivy'],
        'mally': ['malachi', 'mally'],
        'roscoe': ['roscoe', 'ross'],
        'pat': ['patrick', 'pate', 'peter', 'pat', 'patsy', 'paddy'],
        'shelton': ['shelton', 'tony', 'shel', 'shelly'],
        'jennet': ['jennet', 'jessie', 'jenny'],
        'rachel': ['rachel', 'shelly'],
        'edwin': ['edwina', 'edwin'],
        'lucias': ['lucias', 'luke'],
        'hermie': ['hermione', 'hermie'],
        'eric': ['eric', 'rick', 'ricky'],
        'matthew': ['matthew', 'thys', 'matt', 'thias', 'mattie', 'matty'],
        'verna': ['laverne', 'vernon', 'verna'],
        'chrissy': ['christine', 'kris', 'kristy', 'chrissy', 'tina', 'chris', 'crissy'],
        'sybill': ['sybill', 'sibbie'],
        'arzada': ['arzada', 'zaddi'],
        'nada': ['nadine', 'nada', 'deedee'],
        'paula': ['paula', 'polly', 'lina'],
        'drina': ['alexandria', 'drina', 'alexander', 'alla', 'sandra'],
        'jeffrey': ['jeffrey', 'geoff', 'jeff'],
        'raymond': ['raymond', 'ray'],
        'josetta': ['josetta', 'jettie'],
        'edythe': ['edythe', 'edie', 'edye'],
        'leet': ['philetus', 'leet', 'phil'],
        'deidre': ['deidre', 'deedee'],
        'gloria': ['gloria', 'glory'],
        'norah': ['honora', 'honey', 'nora', 'norry', 'norah'],
        'cinderlla': ['cindy', 'cinderlla'],
        'jehu': ['jehu', 'hugh', 'gee'],
        'kimberley': ['kimberley', 'kim'],
        'harty': ['hortense', 'harty', 'tensey'],
        'eurydice': ['eurydice', 'dicey'],
        'valerie': ['valerie', 'val'],
        'relief': ['relief', 'leafa'],
        'alfreda': ['alfreda', 'freddy', 'alfy', 'freda', 'frieda'],
        'con': ['cornelius', 'conny', 'niel', 'corny', 'con'],
        'nessa': ['vanessa', 'essa', 'vanna', 'nessa'],
        'ignatius': ['ignatius', 'natius', 'iggy', 'nate', 'nace'],
        'monet': ['monet', 'nettie'],
        'frankie': ['frankie', 'frank', 'francis'],
        'noah': ['manoah', 'noah'],
        'savannah': ['savannah', 'vannie', 'anna'],
        'toby': ['tobias', 'bias', 'toby'],
        'roxane': ['roxane', 'rox', 'roxie'],
        'gwen': ['gwendolyn', 'gwen', 'wendy'],
        'kill': ['archilles', 'kill', 'killis'],
        'abigail': ['abigail', 'nabby', 'abby', 'gail'],
        'casper': ['jasper', 'jap', 'casper'],
        'paul': ['paul', 'polly', 'paula', 'pauline'],
        'lauren': ['lauren', 'ren', 'laurie'],
        'vessie': ['sylvester', 'sy', 'sly', 'vet', 'syl', 'vester', 'si', 'vessie'],
        'almena': ['almena', 'mena', 'allie'],
        'bedney': ['abednego', 'bedney'],
        'sheldon': ['sheldon', 'shelly'],
        'tim': ['timothy', 'tim', 'timmy'],
        'edye': ['edythe', 'edie', 'edye'],
        'bell': ['william', 'willy', 'bell', 'bela', 'bill', 'will', 'billy', 'willie'],
        'nicodemus': ['nicodemus', 'nick'],
        'pam': ['pamela', 'pam'],
        'nabby': ['abigail', 'nabby', 'abby', 'gail'],
        'kimberly': ['kimberly', 'kim'],
        'ade': ['adam', 'edie', 'ade'],
        'trudy': ['trudy', 'gertrude'],
        'ado': ['adolphus', 'dolph', 'ado', 'adolph'],
        'bela': ['william', 'willy', 'bell', 'bela', 'bill', 'will', 'billy', 'willie'],
        'nate': ['nathaniel', 'than', 'nathan', 'nate', 'nat', 'natty'],
        'ross': ['roscoe', 'ross'],
        'jake': ['jacob', 'jaap', 'jake', 'jay'],
        'fate': ['lafayette', 'laffie', 'fate'],
        'marcus': ['marcus', 'mark'],
        'livia': ['olivia', 'nollie', 'livia', 'ollie'],
        'selma': ['selma', 'anselm'],
        'adolph': ['adolphus', 'dolph', 'ado', 'adolph'],
        'virginia': ['virginia', 'jane', 'jennie', 'ginny', 'virgy', 'ginger'],
        'amy': ['amelia', 'amy', 'mel', 'millie', 'emily'],
        'nando': ['ferdinando', 'nando', 'ferdie', 'fred'],
        'leon': ['napoleon', 'nap', 'nappy', 'leon'],
        'tillie': ['tilford', 'tillie'],
        'lavonne': ['lavonne', 'von'],
        'tick': ['felicity', 'flick', 'tick'],
        'rebecca': ['rebecca', 'beck', 'becca', 'reba', 'becky'],
        'robbie': ['roberta', 'robbie', 'bert', 'bobbie', 'birdie', 'bertie'],
        'valentine': ['valentine', 'felty'],
        'walt': ['walter', 'wally', 'walt'],
        'lincoln': ['lincoln', 'link'],
        'emma': ['emma', 'emmy'],
        'eseneth': ['eseneth', 'senie'],
        'christine': ['christine', 'kris', 'kristy', 'chrissy', 'tina', 'chris', 'crissy'],
        'patrick': ['patrick', 'pate', 'peter', 'pat', 'patsy', 'paddy'],
        'jinsy': ['jinsy', 'jane'],
        'lavonia': ['lavonia', 'vina', 'vonnie', 'wyncha', 'viney'],
        'candy': ['candace', 'candy', 'dacey'],
        'kasey': ['kasey', 'k.c.'],
        'rian': ['adrian', 'rian'],
        'appie': ['appoline', 'appy', 'appie'],
        'martin': ['martin', 'marty'],
        'beverly': ['beverly', 'bev'],
        'chick': ['chick', 'charlotte', 'caroline', 'chuck'],
        'isadora': ['isadora', 'issy', 'dora'],
        'conrad': ['conrad', 'conny', 'con'],
        'emmy': ['emma', 'emmy'],
        'vangie': ['evangeline', 'ev', 'evan', 'vangie'],
        'paulina': ['paulina', 'polly', 'lina'],
        'pauline': ['pauline', 'polly'],
        'eben': ['ebenezer', 'ebbie', 'eben', 'eb'],
        'shel': ['shelton', 'tony', 'shel', 'shelly'],
        'lucy': ['lucy', 'lucinda'],
        'britt': ['brittany', 'britt'],
        'tony': ['tony', 'anthony'],
        'eddie': ['edwin', 'ed', 'eddie', 'win', 'eddy', 'ned'],
        'sher': ['sheryl', 'sher'],
        'deliverance': ['deliverance', 'delly', 'dilly', 'della'],
        'erick': ['roderick', 'rod', 'erick', 'rickie'],
        'peter': ['peter', 'pete', 'pate'],
        'joan': ['johannah', 'hannah', 'jody', 'joan', 'nonie'],
        'tibbie': ['isabelle', 'tibbie', 'nib', 'belle', 'bella', 'nibby', 'ib', 'issy'],
        'kathryn': ['kathryn', 'kathy'],
        'exie': ['experience', 'exie'],
        'arlene': ['arlene', 'arly', 'lena'],
        'sebby': ['sebastian', 'sebby', 'seb'],
        'nollie': ['olivia', 'nollie', 'livia', 'ollie'],
        'elbertson': ['elbertson', 'elbert', 'bert'],
        'scottie': ['scott', 'scotty', 'sceeter', 'squat', 'scottie'],
        'morris': ['morris', 'morey'],
        'aleva': ['aleva', 'levy', 'leve'],
        'alonzo': ['alonzo', 'lon', 'al', 'lonzo'],
        'ellie': ['helene', 'lena', 'ella', 'ellen', 'ellie'],
        'wendy': ['wendy', 'wen'],
        'jereme': ['jerry', 'jereme', 'geraldine'],
        'ephraim': ['ephraim', 'eph'],
        'willie': ['wilson', 'will', 'willy', 'willie'],
        'fanny': ['frances', 'sis', 'cissy', 'frankie', 'franniey', 'fran', 'francie', 'frannie', 'fanny'],
        'vivian': ['vivian', 'vi', 'viv'],
        'christiana': ['christiana', 'kris', 'kristy', 'ann', 'tina', 'christy', 'chris', 'crissy'],
        'francie': ['francine', 'franniey', 'fran', 'frannie', 'francie'],
        'millicent': ['millicent', 'missy', 'milly'],
        'kristin': ['kristin', 'chris'],
        'obed': ['obedience', 'obed', 'beda', 'beedy', 'biddie'],
        'mellia': ['mellony', 'mellia'],
        'francis': ['frankie', 'frank', 'francis'],
        'mellie': ['permelia', 'melly', 'milly', 'mellie'],
        'dicey': ['eurydice', 'dicey'],
        'william': ['wilma', 'william', 'billiewilhelm'],
        'thomas': ['tommy', 'thomas'],
        'justin': ['justin', 'justus', 'justina'],
        'hopkins': ['hopkins', 'hopp', 'hop'],
        'hiel': ['jehiel', 'hiel'],
        'howard': ['howard', 'hal', 'howie'],
        'otha': ['theotha', 'otha'],
        'brittany': ['brittany', 'britt'],
        'francine': ['francine', 'franniey', 'fran', 'frannie', 'francie'],
        'quilla': ['tranquilla', 'trannie', 'quilla'],
        'gregory': ['gregory', 'greg'],
        'mamie': ['mary', 'mamie', 'molly', 'mae', 'polly', 'mitzi'],
        'eustacia': ['eustacia', 'stacia', 'stacy'],
        'sigfrid': ['sigfrid', 'sid'],
        'carolyn': ['carolyn', 'lynn', 'carrie', 'cassie'],
        'almina': ['almina', 'minnie'],
        'sylvester': ['sylvester', 'sy', 'sly', 'vet', 'syl', 'vester', 'si', 'vessie'],
        'terry': ['theresa', 'tessie', 'thirza', 'tessa', 'terry', 'tracy', 'tess', 'thursa'],
        'catherine': ['katarina', 'catherine', 'tina'],
        'merv': ['mervyn', 'merv'],
        'augustus': ['augustus', 'gus', 'austin', 'august'],
        'penelope': ['penelope', 'penny'],
        'marjorie': ['marjorie', 'margy', 'margie'],
        'jasper': ['jasper', 'jap', 'casper'],
        'hubert': ['hubert', 'bert', 'hugh', 'hub'],
        'joyce': ['joyce', 'joy'],
        'dossie': ['eudoris', 'dossie', 'dosie'],
        'nellie': ['petronella', 'nellie'],
        'buren': ['vanburen', 'buren'],
        'celinda': ['celinda', 'linda', 'lynn', 'lindy'],
        'van': ['sullivan', 'sully', 'van'],
        'appy': ['appoline', 'appy', 'appie'],
        'epsey': ['artelepsa', 'epsey'],
        'veronica': ['veronica', 'vonnie', 'ron', 'ronna', 'ronie', 'frony', 'franky', 'ronnie'],
        'cinderella': ['cinderella', 'arilla', 'rella', 'cindy', 'rilla'],
        'lon': ['lon', 'lonzo'],
        'philadelphia': ['philadelphia', 'delphia'],
        'hez': ['hezekiah', 'hy', 'hez', 'kiah'],
        'jannett': ['jannett', 'nettie'],
        'ode': ['otis', 'ode', 'ote'],
        'lainie': ['elaine', 'lainie', 'helen'],
        'lou': ['lucinda', 'lu', 'lucy', 'cindy', 'lou'],
        'annette': ['annette', 'anna', 'nettie'],
        'patricia': ['trisha', 'patricia'],
        'hy': ['hiram', 'hy'],
        'mathilda': ['mathilda', 'tillie', 'patty'],
        'noel': ['nowell', 'noel'],
        'jud': ['judson', 'sonny', 'jud'],
        'margy': ['marjorie', 'margy', 'margie'],
        'trannie': ['tranquilla', 'trannie', 'quilla'],
        'thirza': ['theresa', 'tessie', 'thirza', 'tessa', 'terry', 'tracy', 'tess', 'thursa'],
        'basil': ['bazaleel', 'basil'],
        'haseltine': ['haseltine', 'hassie'],
        'mick': ['mike', 'micky', 'mick', 'michael'],
        'marge': ['marge', 'margery', 'margaret', 'margaretta'],
        'gail': ['abigail', 'nabby', 'abby', 'gail'],
        'montesque': ['montesque', 'monty'],
        'rhodella': ['rhodella', 'della'],
        'hody': ['jahoda', 'hody', 'hodie', 'hoda'],
        'margo': ['margarita', 'maggie', 'meg', 'metta', 'midge', 'greta', 'megan', 'maisie', 'madge', 'marge', 'daisy',
                  'peggie', 'rita', 'margo'],
        'tensey': ['hortense', 'harty', 'tensey'],
        'madie': ['madie', 'madeline', 'madelyn'],
        'esther': ['hester', 'hessy', 'esther', 'hetty'],
        'vonna': ['yvonne', 'vonna'],
        'reuben': ['rube', 'reuben'],
        'glory': ['gloria', 'glory'],
        'louvinia': ['louvinia', 'vina', 'vonnie', 'wyncha', 'viney'],
        'dobbin': ['robert', 'hob', 'hobkin', 'dob', 'rob', 'bobby', 'dobbin', 'bob'],
        'daphie': ['daphne', 'daph', 'daphie'],
        'jacobus': ['jacobus', 'jacob'],
        'katelin': ['katelin', 'kay', 'kate', 'kaye'],
        'laverne': ['laverne', 'vernon', 'verna'],
        'mellony': ['mellony', 'mellia'],
        'darkey': ['dorcus', 'darkey'],
        'manuel': ['manuel', 'emanuel', 'manny'],
        'russ': ['russell', 'russ', 'rusty'],
        'percival': ['percival', 'percy'],
        'jerita': ['jerita', 'rita'],
        'squat': ['scott', 'scotty', 'sceeter', 'squat', 'scottie'],
        'brose': ['ambrose', 'brose'],
        'isaiah': ['isaiah', 'zadie', 'zay'],
        'ab': ['absalom', 'app', 'ab', 'abbie'],
        'jenny': ['jenny', 'jennifer'],
        'johnny': ['john', 'jack', 'johnny', 'jock'],
        'theophilus': ['theophilus', 'ophi'],
        'felix': ['felicia', 'fel', 'felix', 'feli'],
        'al': ['alyssa', 'lissia', 'al', 'ally'],
        'erin': ['aaron', 'erin', 'ronnie', 'ron'],
        'elisha': ['elisha', 'lish', 'eli'],
        'aristotle': ['aristotle', 'telly'],
        'ina': ['lavinia', 'vina', 'viney', 'ina'],
        'thursa': ['theresa', 'tessie', 'thirza', 'tessa', 'terry', 'tracy', 'tess', 'thursa'],
        'angelica': ['angela', 'angelica', 'angelina', 'angel', 'angeline', 'jane', 'angie'],
        'myrtle': ['myrtle', 'myrt', 'myrti', 'mert'],
        'heather': ['heather', 'hetty'],
        'vickie': ['vickie', 'victoria'],
        'thias': ['matthias', 'thys', 'matt', 'thias'],
        'mortimer': ['mortimer', 'mort'],
        'patsy': ['patsy', 'patty'],
        'adolphus': ['adolphus', 'dolph', 'ado', 'adolph'],
        'derrick': ['derrick', 'ricky', 'eric', 'rick'],
        'malachi': ['malachi', 'mally'],
        'es': ['essy', 'es'],
        'riah': ['uriah', 'riah'],
        'effie': ['euphemia', 'effie', 'effy'],
        'ferdinando': ['ferdinando', 'nando', 'ferdie', 'fred'],
        'arry': ['armena', 'mena', 'arry'],
        'elsie': ['elsie', 'elsey'],
        'sully': ['sully', 'sullivan'],
        'tilly': ['matilda', 'tilly', 'maud', 'matty'],
        'renius': ['cyrenius', 'swene', 'cy', 'serene', 'renius', 'cene'],
        'hortense': ['hortense', 'harty', 'tensey'],
        'june': ['junior', 'junie', 'june', 'jr'],
        'miriam': ['miriam', 'mimi', 'mitzi', 'mitzie'],
        'alphinias': ['alphinias', 'alphus'],
        'ote': ['otis', 'ode', 'ote'],
        'margaret': ['marge', 'margery', 'margaret', 'margaretta'],
        'brandy': ['brenda', 'brandy'],
        'marcie': ['marsha', 'marcie', 'mary'],
        'kingsley': ['kingsley', 'king'],
        'rafaela': ['rafaela', 'rafa'],
        'chris': ['kristy', 'chris'],
        'shirl': ['shirley', 'sherry', 'lee', 'shirl'],
        'stal': ['crystal', 'chris', 'tal', 'stal', 'crys'],
        'howie': ['howard', 'hal', 'howie'],
        'cliff': ['clifton', 'tony', 'cliff'],
        'max': ['maxine', 'max'],
        'natalie': ['natalie', 'natty', 'nettie'],
        'viney': ['louvinia', 'vina', 'vonnie', 'wyncha', 'viney'],
        'mert': ['myrtle', 'myrt', 'myrti', 'mert'],
        'cally': ['calpurnia', 'cally'],
        'fritz': ['frederick', 'freddie', 'freddy', 'fritz', 'fred'],
        'raphael': ['raphael', 'ralph'],
        'jebadiah': ['jeb', 'jebadiah'],
        'corey': ['corey', 'coco', 'cordy', 'ree'],
        'elaine': ['helena', 'eileen', 'lena', 'nell', 'nellie', 'eleanor', 'elaine', 'ellen', 'aileen'],
        'adam': ['adam', 'edie', 'ade'],
        'heidi': ['adelaide', 'heidi', 'adele', 'dell', 'addy', 'della'],
        'dyer': ['zedediah', 'dyer', 'zed', 'diah'],
        'wilma': ['wilma', 'william', 'billiewilhelm'],
        'edwina': ['edwina', 'edwin'],
    }

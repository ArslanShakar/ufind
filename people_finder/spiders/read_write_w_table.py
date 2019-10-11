import json
from collections import OrderedDict
from datetime import datetime


def insert_record(person, db_connection, db_cursor):
    addresses = [get_address(address) for address in person['addresses']]

    query = "INSERT INTO `W_USPhoneBook`(" \
            "`Full_Name`, " \
            "`First_Name`, " \
            "`Last_Name`, " \
            "`Middle_Name`, " \
            "`Age`, " \
            "`Phones`, " \
            "`Emails`, " \
            "`Mailing_Address1`, " \
            "`Mailing_City`, " \
            "`Mailing_State`, " \
            "`Mailing_Zip`, " \
            "`PreviousAddresses`, " \
            "`Relatives`, " \
            "`Associates`, " \
            "`PersonInfo`, " \
            "`Link`, " \
            "`LastUpdate`) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"

    val = (person['full_name'],
           person['first_name'],
           person['last_name'],
           person['middle_name'],
           person.get('age', ''),
           get_phones_json(person.get('phones', [])),
           json.dumps(person.get('emails', [])),
           person['addresses'][0]['address1'],
           person['addresses'][0]['city'],
           person['addresses'][0]['state'],
           person['addresses'][0]['zip'],
           json.dumps(addresses),
           json.dumps([]),
           json.dumps([]),
           json.dumps(dict(person.get('person_info', {}))),
           person['link'],
           datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    db_cursor.execute(query, val)
    db_connection.commit()

    return db_cursor.lastrowid


def get_phones_json(phones):
    phones = [
        {
            'number': phone['number'],
            'type': phone.get('type', ''),
            'rank': phone.get('rank', 0)
         } for phone in phones if phone
    ]

    return json.dumps(phones)


def get_address(address_info):
    address = OrderedDict()
    address['address1'] = address_info.get('address1', '')
    address['city'] = address_info.get('city', '')
    address['state'] = address_info.get('state', '')
    address['zip'] = address_info.get('zip', '')
    address['property_hb'] = address_info.get('property_hb', 'Home')
    address['property_ms'] = address_info.get('property_ms', 'Mailing')
    address['property_cp'] = address_info.get('property_cp', 'currentImported')

    return address

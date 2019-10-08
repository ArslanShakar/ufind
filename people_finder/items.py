from scrapy import Item, Field


class PersonItem(Item):
    id = Field()
    pjID = Field()
    search_url = Field()
    full_name = Field()
    first_name = Field()
    middle_name = Field()
    last_name = Field()
    scraper_level = Field()
    prefix = Field()
    suffix = Field()
    link = Field()
    age = Field()
    gender = Field()
    points = Field()
    occupation = Field()
    education = Field()
    party = Field()
    country = Field()
    emails = Field()
    phones = Field()
    addresses = Field()
    relatives = Field()
    associated_persons = Field()
    mailing_address = Field()
    mailing_city = Field()
    mailing_state = Field()
    mailing_zip = Field()
    property_address = Field()
    property_city = Field()
    property_state = Field()
    property_zip = Field()
    person_info = Field()
    property_value = Field()
    construction_year = Field()


class AssociatedPerson(PersonItem):
    type = Field()
    associate_types = Field()


class EmailItem(Item):
    email = Field()
    email_type = Field()


class PhoneItem(Item):
    link = Field()
    rank = Field()
    number = Field()
    type = Field()
    carrier = Field()


class AddressItem(Item):
    link = Field()
    address1 = Field()
    city = Field()
    state = Field()
    zip = Field()
    property_ms = Field()
    property_hb = Field()
    property_cp = Field()


class PersonInfo(PersonItem):
    home_owner_source = Field()
    income_household = Field()
    net_worth = Field()
    new_credit = Field()
    education = Field()
    ethnic_group = Field()

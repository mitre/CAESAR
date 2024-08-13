import arrow
from dateutil.parser import parse

class DateHelper:
    @staticmethod
    def serialize_datetime(dt):
        return arrow.get(dt).format('YYYY-MM-DDTHH:mm') if dt else None
    
    @staticmethod
    def serialize_date(date):
        return arrow.get(date).format('YYYY-MM-DD') if date else None
    
    @staticmethod
    def serialize_time(time):
        if (time):
            if (isinstance(time, str)):
                return time
            
            return time.strftime("%H:%M:%S")

    @staticmethod
    def file_date_parse(dt):
        try:
         d = arrow.get(dt, 'YYYY:MM:DD HH:mm:ss').format('YYYY-MM-DDTHH:mm') if dt else None
         return d
        except Exception as e:
            print (e)
            return None

    @staticmethod
    def parse_datetime(dt):
        try:
            d = arrow.get(dt,'YYYY-MM-DDTHH:mm').datetime.replace(tzinfo=None) if dt else None
            return d
        except Exception as e:
            print(e)
            return None


    @staticmethod
    def parse_date(str_date):
        # Handle pandas naT (null dates values)
        if (str_date != str_date):
            return None
        try:
            d = parse(str(str_date))
            return str(d)
        except Exception as e:
            print (e)
            return None
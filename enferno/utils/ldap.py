from flask_security import LoginForm
from flask_security.utils import hash_password
from ldap3 import Connection

from enferno.settings import Config
from enferno.user.models import User, Role

class LdapLoginForm(LoginForm):

    def validate(self, **kwargs):        
        if Config.LDAP_ENABLE and self.data.get('username') != Config.ADMIN_USERNAME:
          username = self.data.get('username')
          ldap_username = username

          if Config.LDAP_SEC_PROTOTCOL == 'NTLM':
             ldap_username = f"{Config.LDAP_DOMAIN}\\{username}"

          conn = Connection(
              Config.LDAP_SERVER,
              user=ldap_username,
              password=self.data.get('password', ''),
              authentication=Config.LDAP_SEC_PROTOTCOL)
          connected = conn.bind()

          if not connected:
            conn.unbind()
            return False
          
          user = User.query.filter_by(username=username.lower()).first()

          # If the user isn't in our database, build the local user from the external user returned via ldap
          if not user:
            conn.search(
              search_base=Config.LDAP_SEARCH_BASE, 
              search_filter=f'({Config.LDAP_FIELD_UID}={username})',
              attributes=['mail', 'displayname'],
            )
            ldap_record = conn.entries[0]
            if ldap_record:
               createUser(self.data, ldap_record)
          else:
            # Update the user's password to match the LDAP password
            user.password = hash_password(self.data.get('password'))
            result = user.save()

          # Close the LDAP connection
          conn.unbind()
        
        return super().validate(**kwargs)
    
def createUser(login_info, ldap_record):
   user = User()
   user.username = login_info.get('username')
   user.email = ldap_record.mail.value
   user.name = ldap_record.displayName.value
   user.password = hash_password(login_info.get('password'))
   user.active = True

   user.save()

"""Class: AthensdaHelper
"""

from AccessControl.SecurityInfo import ClassSecurityInfo
from App.class_init import default__class_init__ as InitializeClass

from Products.PluggableAuthService.plugins.BasePlugin import BasePlugin
from Products.PluggableAuthService.utils import classImplements
from Products.CMFCore.utils import getToolByName
import interface

## Imported class for plugin implementation
from OFS.Folder import Folder
from Crypto.Cipher import AES
from Crypto.Util import randpool
from datetime import datetime
from urlparse import urlparse
import time
import base64
import urllib

import logging

from zLOG import LOG, INFO
from urlparse import urlparse

from Products.PluggableAuthService.interfaces.plugins import \
        ICredentialsUpdatePlugin

logger = logging.getLogger('pas.plugin.athensda')


class AthensdaHelper(Folder, BasePlugin):
    """Multi-plugin

    """

    meta_type = 'AthensDA Helper'
    security = ClassSecurityInfo()

    # custom attributes
    athens_url = 'https://auth.athensams.net'
    return_url = 'http://www.rcseng.ac.uk'
    org_id = 'urn:mace:eduserv.org.uk:athens:provider:rcseng.ac.uk'
    block_size = 16
    iv_bytes = randpool.RandomPool(512).get_bytes(block_size)
    mode = AES.MODE_CBC

    _properties = ({'id': 'title',
                    'label': 'Title',
                    'type': 'string',
                    'mode': 'w'
                    },
                    {'id': 'athens_url',
                     'label': 'Athens URL',
                     'type': 'string',
                     'mode': 'w',
                     },
                    {'id': 'return_url',
                     'label': 'Return URL',
                     'type': 'string',
                     'mode': 'w',
                     },
                    {'id': 'org_id',
                     'label': 'Organisational identifier',
                     'type': 'string',
                     'mode': 'w',
                     },
                   #{ 'id': 'athens_key',
                   #  'label': 'Key',
                   #  'type': 'string',
                   #  'mode': 'w',
                   #  },
                   )

    manage_options = (BasePlugin.manage_options[:1]
                     + Folder.manage_options[:1]
                     + Folder.manage_options[2:]
                      )

    def __init__(self, id, title=None):
        self._setId(id)
        self.title = title
        logger.info('Engine been at AthensDA PAS Plugin.')

    def _get_return_url(self, request):
        if request.get('came_from'):
            came_from = request.get('came_from') or request.environ['HTTP_REFERER']
        else:
            came_from = request['BASE0']

        scheme, location, path, parameters, query, fragment = urlparse(came_from)
        template_id = path.split('/')[-1]
        if template_id in ['login', 'login_success', 'login_password',
                           'login_failed', 'login_form', 'logged_in', 'logout',
                           'logged_out', 'registered', 'mail_password',
                           'mail_password_form', 'register', 'require_login',
                           'member_search_results', 'pwreset_finish',
                           # We need localhost in the list, or Testing.testbrowser
                           # tests won't be able to log in via login_form
                           'localhost']:
            came_from = ''

        purl = getToolByName(self, 'portal_url')

        if not purl.isURLInPortal(came_from):
            came_from = ''

        if not came_from:
            came_from = purl()  # portal url - site root

        return came_from

    security.declarePrivate('updateCredentials')

    def updateCredentials(self, request, response, login, new_password):
        """ Redirect User to Athens. """

        user = request.AUTHENTICATED_USER
        perm_set = None
        decoded_key = base64.b64decode(self.key+'==')

        if request.get('t') == 'dsr':
            request.response.redirect(self.athens_url + '?' + self.geturl_encoded_string_for_hdd(request, response))
        else:
            try:
                permission_set = self.get_simsathens_permissions(contact_number=user).dictionaries()
            except:
                permission_set = {}

            for permission in permission_set:
                perm_set = permission['permission_set']
            if perm_set:
                athens_response = request.response.redirect(str(self.athens_url + '?' + self.geturl_encoded_string_for_laa(request, response)))

                try:
                    parse_url = urlparse(athens_response)
                    athens_parameter = dict([part.split('=') for part in parse_url[4].split('&')]).get('p')
                    unquoted_string = urllib.unquote(athens_parameter)
                    b64_string = base64.urlsafe_b64decode(unquoted_string)
                    iv_bytes = b64_string[:16]
                    data = b64_string[16:]
                    decrypted_string = AES.new(decoded_key, self.mode, self.iv_bytes).decrypt(data).strip()
                    self.insert_web_auth_log(contact_number=user,
                                             permission_set=None,
                                             url_string=None,
                                             return_url=self._get_return_url(request),
                                             browser=request.environ['HTTP_USER_AGENT'],
                                             ip_address=request.environ['REMOTE_ADDR'],
                                             return_parameter=decrypted_string)
                except:
                    LOG('AthenPASPlugin', INFO, "There is issue with Athens response")
                    pass
            #else:
            #    return

    security.declarePrivate('geturl_encoded_string_for_laa')

    def geturl_encoded_string_for_laa(self, request, response):
        decoded_key = base64.b64decode(self.key+'==')
        perm_set = None
        user = request.AUTHENTICATED_USER

        permission_set = self.get_simsathens_permissions(contact_number=user).dictionaries()

        came_from = self._get_return_url(request)

        for permission in permission_set:
            if permission['permission_set']:
                perm_set = permission['permission_set']

        url_string = "<daa p=\"%s\" u=\"%s\" t=\"%s\" r=\"%s\" n=\"%s\" />" % (
            perm_set,
            user,
            int(time.mktime(datetime.now().timetuple())),
            came_from,
            base64.b64encode(self.iv_bytes))
        pad = self.block_size - len(url_string) % self.block_size
        data = url_string + pad * chr(pad)
        encrypted_string = self.iv_bytes + AES.new(decoded_key, self.mode, self.iv_bytes).encrypt(data)
        base64_encoded_string = base64.b64encode(encrypted_string)
        self.insert_web_auth_log(
            contact_number=user,
            permission_set=perm_set,
            url_string=url_string,
            return_url=came_from,
            browser=request.environ['HTTP_USER_AGENT'],
            ip_address=request.environ['REMOTE_ADDR'],
            return_parameter=None)
        return urllib.urlencode({"t": "daa", "id": self.org_id, "p": base64_encoded_string})

    security.declarePrivate('geturl_encoded_string_for_hdd')

    def geturl_encoded_string_for_hdd(self, request, response):
        user = request.AUTHENTICATED_USER
        perm_set = None
        permission_set = self.get_simsathens_permissions(contact_number=user).dictionaries()
        decoded_key = base64.b64decode(self.key+'==')

        for permission in permission_set:
            if permission['permission_set']:
                perm_set = permission['permission_set']
        url_string = "<dst p=\"%s\" u=\"%s\" d=\"%s\" />" % (perm_set, user, request.get('p'))
        LOG('AthenPASPlugin', INFO, "HDD String is " + str(url_string))
        pad = self.block_size - len(url_string) % self.block_size
        data = url_string + pad * chr(pad)
        encrypted_string = self.iv_bytes + AES.new(decoded_key, self.mode, self.iv_bytes).encrypt(data)
        base64_encoded_string = base64.b64encode(encrypted_string)
        self.insert_web_auth_log(
            contact_number=user,
            permission_set='rcs-cs',
            url_string=url_string,
            return_url=self._get_return_url(request),
            browser=request.environ['HTTP_USER_AGENT'],
            ip_address=request.environ['REMOTE_ADDR'],
            return_parameter=None)
        return urllib.urlencode({"t": "dst", "id": self.org_id, "p": base64_encoded_string})


classImplements(AthensdaHelper, interface.IAthensdaHelper, ICredentialsUpdatePlugin)

InitializeClass(AthensdaHelper)

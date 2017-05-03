import os
import re
import __main__
import webbrowser
import time
import datetime
import urllib2
from storage import RemoteStorage
import flickr_api
from flickr_api.api import flickr
from file_info import FileInfo
from folder_info import FolderInfo
from local_storage import mkdirp

MAX_PAGES = 1000
TOKEN_FILENAME = '.flickrToken'
CHECKSUM_PREFIX = 'checksum:md5'
OAUTH_PERMISSIONS = 'write'

class FlickrStorage(RemoteStorage):

    def __init__(self, config):
        self._config = config
        self._is_authenticated = False
        self._user = None
        self._photosets = {}
        self._photos = {}

    def list_folders(self):
        self._authenticate()
        all_photosets = []
        page = 1
        total_pages = 0
        for i in range(0, MAX_PAGES):
            paged_photosets = self._call_remote(self._user.getPhotosets, page=page)
            all_photosets += paged_photosets
            total_pages = paged_photosets.info.pages
            page = paged_photosets.info.page
            if page >= total_pages:
                break

        self._photosets = {x.id: x for x in all_photosets}
        folders = [FolderInfo(id=x.id, name=x.title) for x in all_photosets]
        return [x for x in folders 
            if (not self._config.include_dir or re.search(self._config.include_dir, x.name, flags=re.IGNORECASE)) and
                (not self._config.exclude_dir or not re.search(self._config.exclude_dir, x.name, flags=re.IGNORECASE))]

    def list_files(self, folder):
        self._authenticate()
        all_photos = []
        page = 1
        total_pages = 0
        if not folder == None:
            operation = self._photosets[folder.id].getPhotos
        else:
            operation = self._user.getNotInSetPhotos
        for i in range(0, MAX_PAGES):
            paged_photos = self._call_remote(operation, extras='original_format,tags')
            all_photos += paged_photos
            total_pages = paged_photos.info.pages
            page = paged_photos.info.page
            if page >= total_pages:
                break

        self._photos.update({x.id: x for x in all_photos})
        print "{!r}".format(all_photos)
        files = [self._get_file_info(x) for x in all_photos]
        return [x for x in files 
            if (not self._config.include or re.search(self._config.include, x.name, flags=re.IGNORECASE)) and
                (not self._config.exclude or not re.search(self._config.exclude, x.name, flags=re.IGNORECASE))]

    def download(self, file_info, dest):
        mkdirp(dest)
        photo = self._photos[file_info.id]
        self._call_remote(photo.save, dest, size_label='Original')

    def upload(self, src, folder_name, file_name, checksum):
        tags = self._config.tags
        if checksum:
            tags = '{} {}={}'.format(tags, CHECKSUM_PREFIX, checksum)
        photo = self._call_remote(
            flickr_api.upload,
            photo_file=src, 
            title=os.path.splitext(file_name)[0], 
            tags=tags.strip(),
            is_public=self._config.is_public,
            is_friend=self._config.is_friend,
            is_family=self._config.is_family,
            async=1)
        # We should put the album assignment on a separate thread. flickr.photos.upload.checkTickets
        # This will mean we need to wait for async operations to finish before completing process.
        # Maybe don't write file name to output until operation is complete

        if folder_name:
            photoset = self._get_folder_by_name(folder_name)
            if not photoset:
                photoset = self._call_remote(flickr_api.Photoset.create, title=folder_name, primary_photo=photo)
            self._call_remote(photoset.addPhoto, photo=photo)

    def copy_file(self, file_info, folder_name, dest_storage):
        if isinstance(dest_storage, RemoteStorage):
            temp_file = NamedTemporaryFile()
            self.download(file_info, temp_file.name)
            dest_storage.upload(temp_file.name, folder_name, file_info.name, file_info.checksum)
            temp_file.close()
        else:
            dest = os.path.join(dest_storage.path, folder_name, file_info.name)
            self.download(file_info, dest)

    def _get_folder_by_name(self, name):
        return next((x for x in self._photosets.values() if x.title.lower() == name.lower()), None)

    def _get_file_info(self, photo):
        name = photo.title if photo.title else photo.id
        checksum = None
        if photo.originalformat:
            name += "." + photo.originalformat
        if photo.tags:
            tags = photo.tags.split()
            checksum = next((parts[1] for parts in (tag.split('=') for tag in tags) if parts[0] == CHECKSUM_PREFIX), None)
        return FileInfo(id=photo.id, name=name, checksum=checksum)

    def _authenticate(self):
        if self._is_authenticated:
            return

        flickr_api.set_keys(api_key = self._config.api_key, api_secret = self._config.api_secret)

        token_path = os.path.join(os.path.split(os.path.abspath(__main__.__file__))[0], TOKEN_FILENAME)
        if os.path.isfile(token_path):
           auth_handler = flickr_api.auth.AuthHandler.load(token_path) 

        else:
            auth_handler = flickr_api.auth.AuthHandler()
            permissions_requested = OAUTH_PERMISSIONS
            url = auth_handler.get_authorization_url(permissions_requested)
            webbrowser.open(url)
            print "Please enter the OAuth verifier tag once logged in:"
            verifier_code = raw_input("> ")
            auth_handler.set_verifier(verifier_code)
            auth_handler.save(token_path)

        flickr_api.set_auth_handler(auth_handler)
        self._user = flickr_api.test.login()
        self._is_authenticated = True

    def _call_remote(self, fn, *args, **kwargs):
        backoff = [0, 1, 3, 5, 10, 30, 60]
        if self._config.throttling > 0:
            time.sleep(self._config.throttling)
        for i in range(self._config.retry):
            if i > 0:
                time.sleep(backoff[i] if i < len(backoff) else backoff[-1])
            try:
                return fn(*args, **kwargs)
            except urllib2.URLError:
                pass
        return fn(*args, **kwargs)

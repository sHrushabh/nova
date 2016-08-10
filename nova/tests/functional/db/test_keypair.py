#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from nova import context
from nova.db.sqlalchemy import api as db_api
from nova import exception
from nova import objects
from nova.objects import keypair
from nova import test
from nova.tests import fixtures


class KeyPairObjectTestCase(test.NoDBTestCase):
    USES_DB_SELF = True

    def setUp(self):
        super(KeyPairObjectTestCase, self).setUp()
        self.useFixture(fixtures.Database())
        self.useFixture(fixtures.Database(database='api'))
        self.context = context.RequestContext('fake-user', 'fake-project')

    def _api_kp(self, **values):
        kp = objects.KeyPair(context=self.context,
                             user_id=self.context.user_id,
                             name='fookey',
                             fingerprint='fp',
                             public_key='keydata',
                             type='ssh')
        kp.update(values)
        kp.create()
        return kp

    def _main_kp(self, **values):
        vals = {
            'user_id': self.context.user_id,
            'name': 'fookey',
            'fingerprint': 'fp',
            'public_key': 'keydata',
            'type': 'ssh',
        }
        vals.update(values)
        return db_api.key_pair_create(self.context, vals)

    def test_create_in_api(self):
        kp = self._api_kp()
        keypair.KeyPair._get_from_db(self.context, kp.user_id, kp.name)
        self.assertRaises(exception.KeypairNotFound,
                          db_api.key_pair_get,
                          self.context, kp.user_id, kp.name)

    def test_create_in_api_duplicate(self):
        self._api_kp()
        self.assertRaises(exception.KeyPairExists, self._api_kp)

    def test_create_in_api_duplicate_in_main(self):
        self._main_kp()
        self.assertRaises(exception.KeyPairExists, self._api_kp)

    def test_get_from_api(self):
        self._api_kp(name='apikey')
        self._main_kp(name='mainkey')
        kp = objects.KeyPair.get_by_name(self.context, self.context.user_id,
                                         'apikey')
        self.assertEqual('apikey', kp.name)

    def test_get_from_main(self):
        self._api_kp(name='apikey')
        self._main_kp(name='mainkey')
        kp = objects.KeyPair.get_by_name(self.context, self.context.user_id,
                                         'mainkey')
        self.assertEqual('mainkey', kp.name)

    def test_get_not_found(self):
        self._api_kp(name='apikey')
        self._main_kp(name='mainkey')
        self.assertRaises(exception.KeypairNotFound,
                          objects.KeyPair.get_by_name,
                          self.context, self.context.user_id, 'nokey')

    def test_destroy_in_api(self):
        kp = self._api_kp(name='apikey')
        self._main_kp(name='mainkey')
        kp.destroy()
        self.assertRaises(exception.KeypairNotFound,
                          objects.KeyPair.get_by_name,
                          self.context, self.context.user_id, 'apikey')

    def test_destroy_by_name_in_api(self):
        self._api_kp(name='apikey')
        self._main_kp(name='mainkey')
        objects.KeyPair.destroy_by_name(self.context, self.context.user_id,
                                        'apikey')
        self.assertRaises(exception.KeypairNotFound,
                          objects.KeyPair.get_by_name,
                          self.context, self.context.user_id, 'apikey')

    def test_destroy_in_main(self):
        self._api_kp(name='apikey')
        self._main_kp(name='mainkey')
        kp = objects.KeyPair.get_by_name(self.context, self.context.user_id,
                                         'mainkey')
        kp.destroy()
        self.assertRaises(exception.KeypairNotFound,
                          objects.KeyPair.get_by_name,
                          self.context, self.context.user_id, 'mainkey')

    def test_destroy_by_name_in_main(self):
        self._api_kp(name='apikey')
        self._main_kp(name='mainkey')
        objects.KeyPair.destroy_by_name(self.context, self.context.user_id,
                                        'mainkey')

    def test_get_by_user(self):
        self._api_kp(name='apikey')
        self._main_kp(name='mainkey')
        kpl = objects.KeyPairList.get_by_user(self.context,
                                              self.context.user_id)
        self.assertEqual(2, len(kpl))
        self.assertEqual(set(['apikey', 'mainkey']),
                         set([x.name for x in kpl]))

    def test_get_count_by_user(self):
        self._api_kp(name='apikey')
        self._main_kp(name='mainkey')
        count = objects.KeyPairList.get_count_by_user(self.context,
                                                      self.context.user_id)
        self.assertEqual(2, count)

    def test_migrate_keypairs(self):
        self._api_kp(name='apikey')
        self._main_kp(name='mainkey1')
        self._main_kp(name='mainkey2')
        self._main_kp(name='mainkey3')
        total, done = keypair.migrate_keypairs_to_api_db(self.context, 2)
        self.assertEqual(2, total)
        self.assertEqual(2, done)

        # NOTE(danms): This only fetches from the API DB
        api_keys = objects.KeyPairList._get_from_db(self.context,
                                                    self.context.user_id,
                                                    limit=None,
                                                    marker=None)
        self.assertEqual(3, len(api_keys))

        # NOTE(danms): This only fetches from the main DB
        main_keys = db_api.key_pair_get_all_by_user(self.context,
                                                    self.context.user_id)
        self.assertEqual(1, len(main_keys))

        self.assertEqual((1, 1),
                         keypair.migrate_keypairs_to_api_db(self.context, 100))
        self.assertEqual((0, 0),
                         keypair.migrate_keypairs_to_api_db(self.context, 100))

    def test_migrate_keypairs_bails_on_unmigrated_instances(self):
        objects.Instance(context=self.context, user_id=self.context.user_id,
                         project_id=self.context.project_id).create()
        self._api_kp(name='apikey')
        self._main_kp(name='mainkey1')
        total, done = keypair.migrate_keypairs_to_api_db(self.context, 100)
        self.assertEqual(0, total)
        self.assertEqual(0, done)

    def test_migrate_keypairs_skips_existing(self):
        self._api_kp(name='mykey')
        self._main_kp(name='mykey')
        total, done = keypair.migrate_keypairs_to_api_db(self.context, 100)
        self.assertEqual(1, total)
        self.assertEqual(1, done)
        total, done = keypair.migrate_keypairs_to_api_db(self.context, 100)
        self.assertEqual(0, total)
        self.assertEqual(0, done)

    def test_get_by_user_limit_and_marker(self):
        self._api_kp(name='apikey1')
        self._api_kp(name='apikey2')
        self._main_kp(name='mainkey1')
        self._main_kp(name='mainkey2')

        # check all 4 keypairs (2 api and 2 main)
        kpl = objects.KeyPairList.get_by_user(self.context,
                                              self.context.user_id)
        self.assertEqual(4, len(kpl))
        self.assertEqual(set(['apikey1', 'apikey2', 'mainkey1', 'mainkey2']),
                         set([x.name for x in kpl]))

        # check only 1 keypair (1 api)
        kpl = objects.KeyPairList.get_by_user(self.context,
                                              self.context.user_id,
                                              limit=1)
        self.assertEqual(1, len(kpl))
        self.assertEqual(set(['apikey1']),
                         set([x.name for x in kpl]))

        # check only 3 keypairs (2 api and 1 main)
        kpl = objects.KeyPairList.get_by_user(self.context,
                                              self.context.user_id,
                                              limit=3)
        self.assertEqual(3, len(kpl))
        self.assertEqual(set(['apikey1', 'apikey2', 'mainkey1']),
                         set([x.name for x in kpl]))

        # check keypairs after 'apikey1' (1 api and 2 main)
        kpl = objects.KeyPairList.get_by_user(self.context,
                                              self.context.user_id,
                                              marker='apikey1')
        self.assertEqual(3, len(kpl))
        self.assertEqual(set(['apikey2', 'mainkey1', 'mainkey2']),
                         set([x.name for x in kpl]))

        # check keypairs after 'mainkey2' (no keypairs)
        kpl = objects.KeyPairList.get_by_user(self.context,
                                              self.context.user_id,
                                              marker='mainkey2')
        self.assertEqual(0, len(kpl))

        # check only 2 keypairs after 'apikey1' (1 api and 1 main)
        kpl = objects.KeyPairList.get_by_user(self.context,
                                              self.context.user_id,
                                              limit=2,
                                              marker='apikey1')
        self.assertEqual(2, len(kpl))
        self.assertEqual(set(['apikey2', 'mainkey1']),
                         set([x.name for x in kpl]))

        # check non-existing keypair
        self.assertRaises(exception.MarkerNotFound,
                          objects.KeyPairList.get_by_user,
                          self.context, self.context.user_id,
                          limit=2, marker='unknown_kp')

    def test_get_by_user_different_users(self):
        # create keypairs for two users
        self._api_kp(name='apikey', user_id='user1')
        self._api_kp(name='apikey', user_id='user2')
        self._main_kp(name='mainkey', user_id='user1')
        self._main_kp(name='mainkey', user_id='user2')

        # check all 2 keypairs for user1 (1 api and 1 main)
        kpl = objects.KeyPairList.get_by_user(self.context, 'user1')
        self.assertEqual(2, len(kpl))
        self.assertEqual(set(['apikey', 'mainkey']),
                         set([x.name for x in kpl]))

        # check all 2 keypairs for user2 (1 api and 1 main)
        kpl = objects.KeyPairList.get_by_user(self.context, 'user2')
        self.assertEqual(2, len(kpl))
        self.assertEqual(set(['apikey', 'mainkey']),
                         set([x.name for x in kpl]))

        # check only 1 keypair for user1 (1 api)
        kpl = objects.KeyPairList.get_by_user(self.context, 'user1', limit=1)
        self.assertEqual(1, len(kpl))
        self.assertEqual(set(['apikey']),
                         set([x.name for x in kpl]))

        # check keypairs after 'apikey' for user2 (1 main)
        kpl = objects.KeyPairList.get_by_user(self.context, 'user2',
                                              marker='apikey')
        self.assertEqual(1, len(kpl))
        self.assertEqual(set(['mainkey']),
                         set([x.name for x in kpl]))

        # check only 2 keypairs after 'apikey' for user1 (1 main)
        kpl = objects.KeyPairList.get_by_user(self.context,
                                              'user1',
                                              limit=2,
                                              marker='apikey')
        self.assertEqual(1, len(kpl))
        self.assertEqual(set(['mainkey']),
                         set([x.name for x in kpl]))

        # check non-existing keypair for user2
        self.assertRaises(exception.MarkerNotFound,
                          objects.KeyPairList.get_by_user,
                          self.context, 'user2',
                          limit=2, marker='unknown_kp')
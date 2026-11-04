import unittest
from unittest.mock import patch
from ffxiv_furniture.classification.client import Client
from ffxiv_furniture.classification.contracts import visual_response_format


class StructuredOutputTests(unittest.TestCase):
    def test_active_keys_only_and_exact_shape(self):
        vocab={'concepts':[{'key':'color:red','status':'accepted'},
            {'key':'color:old','status':'merged'}, {'key':'style:carved','status':'provisional','superseded_by':'ornament:carved'}]}
        fmt=visual_response_format(['R002I0001'],'guided',vocab)
        item=fmt['json_schema']['schema']['properties']['items']['items']
        tag=item['properties']['tags']['items']
        self.assertEqual(tag['properties']['key']['enum'],['color:red'])
        self.assertFalse(tag['additionalProperties'])
        self.assertEqual(set(tag['required']),{'key','confidence','evidence'})
        self.assertEqual(item['properties']['id']['enum'],['R002I0001'])
        self.assertEqual(item['properties']['proposed_tags']['maxItems'],6)
        self.assertEqual(visual_response_format(['x'],'final',vocab)['json_schema']['schema']['properties']['items']['items']['properties']['proposed_tags']['maxItems'],0)

    def test_client_transmits_schema_and_thinking_policy(self):
        c=Client('http://localhost/v1','test',enable_thinking=False,structured_output=True)
        c.response_format=visual_response_format(['x'],'explore')
        with patch.object(c,'_request',return_value={}) as send:
            c.chat([])
        payload=send.call_args.args[1]
        self.assertEqual(payload['response_format'],c.response_format)
        self.assertEqual(payload['chat_template_kwargs'],{'enable_thinking':False})

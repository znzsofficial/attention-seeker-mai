import importlib.util
import pathlib
import sys
import tomllib
import types
import unittest
from unittest.mock import AsyncMock, Mock


@unittest.skipUnless(importlib.util.find_spec('maibot_sdk'), 'requires MaiBot SDK')
class LifeIntentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.root = pathlib.Path(__file__).parent
        pkg = types.ModuleType('lonely_intent_test')
        pkg.__path__ = [str(self.root)]
        sys.modules[pkg.__name__] = pkg
        spec = importlib.util.spec_from_file_location('lonely_intent_test.plugin', self.root / 'plugin.py')
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        self.mod = mod
        class Bot(mod.LonelyMaiPlugin):
            config = mod.LonelyMaiConfig()
            ctx = types.SimpleNamespace(logger=Mock(), maisaka=types.SimpleNamespace(
                proactive=types.SimpleNamespace(trigger=AsyncMock())))
        self.bot = Bot()
        self.state = mod.ChatStreamState('chat', 'target')

    async def test_default_life_intent_uses_same_planner_path(self):
        self.assertTrue(await self.bot._do_proactive_chat(self.state, 'target'))
        kw = self.bot.ctx.maisaka.proactive.trigger.call_args.kwargs
        self.assertEqual(kw['stream_id'], 'chat')
        self.assertEqual(kw['intent'], self.bot.config.intent.text)
        self.assertIn('主动分享一点自己的生活', kw['intent'])
        self.assertIn('不要催回复', kw['intent'])
        self.assertIn('未执行', kw['intent'])
        self.assertEqual(kw['reason'], 'attention_proactive')
        self.assertEqual(kw['metadata'], {'source': 'lonelymai', 'target_id': 'target'})

    async def test_custom_intent_is_not_replaced_or_extended(self):
        self.bot.config.intent.text = '自定义意图'
        self.bot.config.intent.reason = 'custom_reason'
        await self.bot._do_proactive_chat(self.state, 'target')
        kw = self.bot.ctx.maisaka.proactive.trigger.call_args.kwargs
        self.assertEqual(kw['intent'], '自定义意图')
        self.assertEqual(kw['reason'], 'custom_reason')

    def test_template_uses_complete_default_and_stays_disabled(self):
        template = tomllib.loads((self.root / 'config.toml').read_text(encoding='utf-8'))
        self.assertEqual(template['intent']['text'], self.bot.config.intent.text)
        self.assertFalse(template['plugin']['enabled'])
        self.assertEqual(template['plugin']['config_version'], '2.0.0')
        self.assertEqual(template['plugin']['version'], '2.0.2')

    async def test_trigger_exception_is_reported_as_failure(self):
        self.bot.ctx.maisaka.proactive.trigger.side_effect = RuntimeError('test')
        self.assertFalse(await self.bot._do_proactive_chat(self.state, 'target'))

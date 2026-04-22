from django.test import TestCase
from core.assistant_parser import HeuristicAssistantQueryParser


class AssistantV2Tests(TestCase):

    def setUp(self):
        self.parser = HeuristicAssistantQueryParser()

    def test_budget_filter_not_unsupported(self):
        result = self.parser.parse("show me cheap restaurants", language="en")
        self.assertNotIn("budget", result.unsupported_filters)

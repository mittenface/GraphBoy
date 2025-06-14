import unittest
from backend.utils import emit

class TestEmitFunction(unittest.TestCase):

    def test_emit_responseText(self):
        message = "Hello, world!"
        expected_output = {
            "responseText": message,
            "responseStream": "",
            "error": False,
        }
        self.assertEqual(emit("responseText", message), expected_output)

    def test_emit_responseStream(self):
        stream_data = "Stream chunk 1"
        expected_output = {
            "responseText": "",
            "responseStream": stream_data,
            "error": False,
        }
        self.assertEqual(emit("responseStream", stream_data), expected_output)

    def test_emit_error_boolean(self):
        error_status = True
        expected_output = {
            "responseText": "",
            "responseStream": "",
            "error": error_status,
        }
        self.assertEqual(emit("error", error_status), expected_output)

    def test_emit_error_string(self):
        error_message = "An error occurred"
        expected_output = {
            "responseText": "",
            "responseStream": "",
            "error": error_message,
        }
        self.assertEqual(emit("error", error_message), expected_output)

    def test_emit_unknown_outputName(self):
        # Test how emit handles an output_name it doesn't explicitly know.
        # Based on current implementation, it should return the default
        # structure and print a warning (though we can't test stdout print
        # here easily).
        unknown_name = "unknownOutput"
        value = "some value"
        expected_output = {
            "responseText": "",
            "responseStream": "",
            "error": False,
        }
        # We are checking that it returns the default structure.
        # The warning print is a side effect not easily testable in this
        # context without redirecting stdout or more complex mocking.
        self.assertEqual(emit(unknown_name, value), expected_output)

    def test_emit_empty_value_responseText(self):
        message = ""
        expected_output = {
            "responseText": message,
            "responseStream": "",
            "error": False,
        }
        self.assertEqual(emit("responseText", message), expected_output)

    def test_emit_empty_value_responseStream(self):
        stream_data = ""
        expected_output = {
            "responseText": "",
            "responseStream": stream_data,
            "error": False,
        }
        self.assertEqual(emit("responseStream", stream_data), expected_output)

    def test_emit_error_false(self):
        error_status = False
        expected_output = {
            "responseText": "",
            "responseStream": "",
            "error": error_status,
        }
        self.assertEqual(emit("error", error_status), expected_output)

if __name__ == '__main__':
    unittest.main()

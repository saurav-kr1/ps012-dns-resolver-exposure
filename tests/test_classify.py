import unittest

from probe.classify import classify_attempt, majority_vote
from probe.config import RECURSIVE, AUTH_ONLY, REFUSED, INCONCLUSIVE
from probe.probes import ProbeResult

TXT = "aiori-probe-ok"


def reply(rcode="NOERROR", ra=False, aa=False, answers=None, rd=True):
    return ProbeResult(qname="x", qtype="TXT", rd=rd, ok=True, rcode=rcode, ra=ra, aa=aa, answers=answers or [])


def silent():
    return ProbeResult(qname="x", qtype="TXT", rd=True, ok=False, error="timeout")


class ClassifyTests(unittest.TestCase):
    def test_open_resolver(self):
        r1 = reply(ra=True, answers=[f'"{TXT}"'])
        self.assertEqual(classify_attempt(r1, None, TXT)[0], RECURSIVE)

    def test_log_confirmation_changes_only_the_reason(self):
        r1 = reply(ra=True, answers=[f'"{TXT}"'])
        self.assertEqual(classify_attempt(r1, None, TXT, True), (RECURSIVE, "resolved+log_confirmed"))
        self.assertEqual(classify_attempt(r1, None, TXT, False), (RECURSIVE, "resolved_no_log_entry"))

    def test_refused_resolver(self):
        self.assertEqual(classify_attempt(reply(rcode="REFUSED"), None, TXT), (REFUSED, "rcode_refused"))

    def test_authoritative_only_is_checked_before_refused(self):
        r1 = reply(rcode="REFUSED")
        r2 = reply(aa=True, answers=["soa"], rd=False)
        self.assertEqual(classify_attempt(r1, r2, TXT)[0], AUTH_ONLY)

    def test_no_reply_is_inconclusive(self):
        self.assertEqual(classify_attempt(silent(), None, TXT), (INCONCLUSIVE, "no_response"))

    def test_servfail_is_inconclusive_not_recursive(self):
        self.assertEqual(classify_attempt(reply(rcode="SERVFAIL", ra=True), None, TXT), (INCONCLUSIVE, "servfail"))

    def test_ra_without_answer(self):
        self.assertEqual(classify_attempt(reply(rcode="NXDOMAIN", ra=True), None, TXT), (INCONCLUSIVE, "ra_no_answer"))

    def test_forwarder_with_aa_flag_needs_log_confirmation(self):
        # dnsmasq copies the upstream's AA bit; only the test-zone log can prove it recursed
        r1 = reply(ra=True, aa=True, answers=[f'"{TXT}"'])
        self.assertEqual(classify_attempt(r1, None, TXT, True), (RECURSIVE, "resolved+log_confirmed"))
        self.assertEqual(classify_attempt(r1, None, TXT, None), (INCONCLUSIVE, "aa_set_unconfirmed"))
        self.assertEqual(classify_attempt(r1, None, TXT, False), (INCONCLUSIVE, "aa_set_unconfirmed"))

    def test_correct_answer_without_recursion_flag_is_not_recursive(self):
        r1 = reply(ra=False, answers=[f'"{TXT}"'])
        self.assertNotEqual(classify_attempt(r1, None, TXT)[0], RECURSIVE)


class VoteTests(unittest.TestCase):
    def test_majority_wins(self):
        a = [(RECURSIVE, "resolved"), (RECURSIVE, "resolved"), (INCONCLUSIVE, "no_response")]
        self.assertEqual(majority_vote(a)[:2], (RECURSIVE, "resolved"))

    def test_no_majority_is_inconclusive(self):
        a = [(RECURSIVE, "resolved"), (REFUSED, "rcode_refused"), (INCONCLUSIVE, "no_response")]
        self.assertEqual(majority_vote(a)[:2], (INCONCLUSIVE, "no_majority"))

    def test_tie_is_inconclusive(self):
        a = [(RECURSIVE, "resolved"), (REFUSED, "rcode_refused")]
        self.assertEqual(majority_vote(a)[0], INCONCLUSIVE)


if __name__ == "__main__":
    unittest.main()

import time


class SensitiveBoomAgent:
    def reset(self):
        pass

    def respond(self, _prompt):
        key = "sk-" + "testtesttesttesttesttest"
        email = "owner" + "@example.com"
        query = "sig" + "=secret"
        raise RuntimeError(f"token {key} email {email} url https://example.invalid/path?{query}")


class SlowAgent:
    def reset(self):
        pass

    def respond(self, prompt):
        time.sleep(0.25)
        return f"Echo: {prompt}"

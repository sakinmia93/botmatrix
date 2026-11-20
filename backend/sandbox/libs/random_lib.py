import random as _random
import string as _string
import secrets as _secrets
import uuid as _uuid


class RandomLib:
    """TBC-compatible libs.Random / libs.random — full method set from docs."""

    # ---- numbers ----
    def randomInt(self, a, b=None):
        if b is None:
            a, b = 0, a
        return _random.randint(int(a), int(b))

    def randomInteger(self, a, b=None):
        return self.randomInt(a, b)

    def randint(self, a, b=None):
        return self.randomInt(a, b)

    def randomFloat(self, a=0.0, b=1.0):
        return _random.uniform(float(a), float(b))

    def random(self):
        return _random.random()

    def randomGaussian(self, mean=0.0, stddev=1.0):
        return _random.gauss(float(mean), float(stddev))

    def randomRange(self, start, stop, count=1):
        """`count` unique integers sampled from [start, stop]."""
        pool = range(int(start), int(stop) + 1)
        k = int(count)
        if k > len(pool):
            raise ValueError("count is larger than the number of values in the range")
        return _random.sample(pool, k)

    def randomBoolean(self):
        return _random.choice([True, False])

    # ---- strings ----
    def randomStr(self, length=8, chars=None, charSet=None):
        pool = chars or charSet or (_string.ascii_letters + _string.digits)
        return "".join(_random.choice(pool) for _ in range(int(length)))

    def randomString(self, length=8, chars=None, charSet=None):
        return self.randomStr(length, chars=chars, charSet=charSet)

    def string(self, length=8, digits=True, letters=True):
        pool = (_string.ascii_letters if letters else "") + (_string.digits if digits else "")
        pool = pool or _string.ascii_letters
        return "".join(_random.choice(pool) for _ in range(int(length)))

    def randomAscii(self, length=8):
        return "".join(_random.choice(_string.ascii_letters) for _ in range(int(length)))

    def randomHex(self, length=16):
        return _secrets.token_hex(max(1, int(length) // 2))[: int(length)]

    def randomBytes(self, length=16):
        return _secrets.token_bytes(int(length))

    def randomUUID(self):
        return str(_uuid.uuid4())

    def uuid(self):
        return self.randomUUID()

    def randomPassword(self, length=12, use_digits=True, use_specials=True, special=None):
        if special is not None:
            use_specials = special
        pool = _string.ascii_letters + (_string.digits if use_digits else "") + ("!@#$%^&*()-_=+" if use_specials else "")
        return "".join(_secrets.choice(pool) for _ in range(int(length)))

    # ---- collections ----
    def randomChoice(self, data):
        return _random.choice(list(data))

    def choice(self, seq):
        return self.randomChoice(seq)

    def randomSample(self, data, k=1):
        data = list(data)
        k = min(int(k), len(data))
        return _random.sample(data, k)

    def randomShuffle(self, data):
        lst = list(data)
        _random.shuffle(lst)
        return lst

    def shuffle(self, seq):
        return self.randomShuffle(seq)

    def randomWeightedChoice(self, data, weights=None):
        """Pick one element according to weights (TBC docs)."""
        data = list(data)
        if not data:
            return None
        if weights is None:
            return _random.choice(data)
        weights = list(weights)
        if len(weights) != len(data):
            # pad or truncate
            if len(weights) < len(data):
                weights = weights + [1] * (len(data) - len(weights))
            else:
                weights = weights[: len(data)]
        # handle zero/negative weights safely
        safe = [max(0.0, float(w)) for w in weights]
        total = sum(safe)
        if total <= 0:
            return _random.choice(data)
        r = _random.uniform(0, total)
        upto = 0.0
        for item, w in zip(data, safe):
            upto += w
            if r <= upto:
                return item
        return data[-1]


    def weightedChoice(self, data, weights=None):
        return self.randomWeightedChoice(data, weights=weights)

    def __getattr__(self, name):
        """Docs: every function is also available in lowercase (randomint, randomchoice, ...)."""
        low = name.lower()
        for n in dir(type(self)):
            if n.lower() == low and not n.startswith("_"):
                return getattr(self, n)
        raise AttributeError(name)

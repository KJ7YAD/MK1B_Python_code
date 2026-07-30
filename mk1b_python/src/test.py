class testSys:
    lastPressure = 0.0

    def __init__(self):
        self.data = open("../test.txt", "rt")

    def ledOn(self):
        print("LED ON")

    def readPressure(self) -> float:
        try:
            l = float(self.data.readline())
            lastPressure = l
        except Exception as e:
            l = lastPressure
        return l

    def ledOff(self):
        print("LED OFF")

    def pyroTest(self) -> bool:
        print("pyro pass")
        return True

    def firePyro1(self):
        print("fire pyro 1")

    def firePyro2(self):
        print("fire pyro 2")

    def safeAllPyros(self):
        print("pyro safe")

    def speak(self, msg):
        print("speak : " + msg)

    def readTemperature(self) -> float:
        return 25.0

    def finish(self):
        print("finished")

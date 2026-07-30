import json


class configuration:
    def __init__(self):
        f = open("config.json")
        self.data = json.load(f)
        f.close()

    def getHistory(self) -> int:
        return self.data["history"]

    def getLaunchDetection(self) -> float:
        return self.data["launchDetect"]

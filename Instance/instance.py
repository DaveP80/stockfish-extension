class InstanceInfo:
    def __init__(self):
        self.info = {}

    def set_info(self, key: str, value: str):
        self.info[key] = value

    def get_info(self, key: str):
        return self.info.get(key)

# Instantiate the class to hold instance information
instance_info = InstanceInfo()

# Dependency to inject instance_info into endpoints
def get_instance_info():
    print(instance_info.info)
    return instance_info

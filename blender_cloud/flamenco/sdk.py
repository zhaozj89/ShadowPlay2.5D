from pillarsdk.resource import List, Find, Create


class Manager(List, Find):
    """Manager class wrapping the REST nodes endpoint"""
    path = 'flamenco/managers'


class Job(List, Find, Create):
    """Job class wrapping the REST nodes endpoint
    """
    path = 'flamenco/jobs'
    ensure_query_projections = {'project': 1}

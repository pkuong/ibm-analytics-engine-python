from __future__ import absolute_import
from __future__ import print_function

from .dataplatform_api import DataPlatformAPI
from .cf.client import CloudFoundryException
from .logger import Logger

"""
.. module:: iae
   :platform: Unix, Windows
   :synopsis: Classes for working with IBM Analytics Engine

.. moduleauthor:: Chris Snow <chsnow123@gmail.com>


"""

class IAEServicePlanGuid:
    """Service Plan Guid for IBM Analytics Engine."""

    LITE = 'acb06a56-fab1-4cb1-a178-c811bc676164'
    """IBM Analytics Engine 'Lite' plan."""

    STD_HOURLY = '9ba7e645-fce1-46ad-90dc-12655bc45f9e'
    """IBM Analytics Engine 'Standard Hourly' plan."""

    STD_MONTHLY = 'f801e166-2c73-4189-8ebb-ef7c1b586709'
    """IBM Analytics Engine 'Standard Monthly' plan."""

    guids = [ LITE, STD_HOURLY, STD_MONTHLY ]

class IAEClusterSpecificationExamples:
    """Example cluster specifications"""

    SINGLE_NODE_BASIC_SPARK = {
        "num_compute_nodes": 1,
        "hardware_config": "default",
        "software_package": "ae-1.0-spark"
    }
    """Basic single node spark cluster with default hardware."""

    SINGLE_NODE_BASIC_HADOOP = {
        "num_compute_nodes": 1,
        "hardware_config": "default",
        "software_package": "ae-1.0-hadoop-spark"
    }
    """Basic single node hadoop cluster with default hardware."""

class IAE:
    """
    This class provides methods for working with IBM Analytics Engine (IAE) deployment operations.  
    Many of the methods in this calls are performed by calling the Cloud Foundry Rest API (https://apidocs.cloudfoundry.org/272/).
    The Cloud Foundry API is quite abstract, so this class provides methods names that are more meaningful for those just wanting to work with IAE.

    This class does not save the state from the Cloud Foundry operations - it retrieve all state from Cloud Foundry as required.
    """


    def __init__(self, cf_client):
        """
        Create a new instance of the IAE client.

        Args:
            cf_client (CloudFoundryAPI): The object that makes the Cloud Foundry rest API calls.
        """

        assert cf_client is not None, "This action requires a CloudFoundryAPI instance"

        if cf_client:
            self.cf_client = cf_client

        self.dataplatform_api = DataPlatformAPI(cf_client)

        self.log = Logger().get_logger(self.__class__.__name__)

    #
    # generic cluster operations
    #

    # TODO create an class for the last_operation_status
    def clusters(self, space_guid, short=True, status=None):
        """
        Returns a list of clusters in the `space_guid`

        Args:
            space_guid (:obj:`str`): The space_guid to query for IAE clusters.
            short (:obj:`bool`, optional): Whether to return short (brief) output.  If false, returns the full Cloud Foundry API output.
            status (:obj:`str`, optional): Filter the return only the provided status values.

        Returns:
            :obj:`list`: If the `short=True`, this method returns: `[ (cluster_name, cluster_guid, last_operation_state), ...  ]`

                | The `last_operation_status` may be:
                | 
                | - `in progress`
                | - `succeeded`
                | - `failed`

        """

        # TODO pass IAEServicePlanGuid.guids to the filter parameter in the cf api call
        iae_instances = self.cf_client.service_instances.get_service_instances(
            space_guid)

        clusters = []
        for i in iae_instances:
            try:
                if i['service_plan']['guid'] in IAEServicePlanGuid.guids:
                    if status is None or status == i['last_operation']['state']:
                        if short:
                            clusters.append({ 
                                      'name': i['name'], 
                                      'guid': i['guid'], 
                                      'state': i['last_operation']['state']
                                    })
                        else:
                            clusters.append(i)
            except KeyError:
                pass
        return clusters

    # TODO what is returned on error?
    def create_cluster(
            self,
            service_instance_name,
            service_plan_guid,
            space_guid,
            cluster_creation_parameters):
        """
        Create a new IAE Cluster`

        Args:
            service_instance_name (:obj:`str`): The name you would like for the Cluster.
            service_plan_guid (:obj:`IAEServicePlanGuid`): The guid representing the type of Cluster to create.
            space_guid (:obj:`str`): The space guid where the Cluster will be created.
            cluster_creation_parameters (:obj:`dict`): The cluster creation parameters.  An example cluster creation parameters is shown below:
        
             | {
             |     "num_compute_nodes": 1,
             |     "hardware_config": "Standard",
             |     "software_package": "ae-1.0-spark",
             |     "customization": [{
             |         "name": "action1",
             |         "type": "bootstrap",
             |         "script": {
             |             "source_type": "http",
             |             "script_path": "http://path/to/your/script"
             |             },
             |         "script_params": []
             |         }]
             | }

        Returns:
            :obj:`str`: The cluster_instance_guid

        """

        # Create instance
        response = self.cf_client.service_instances.provision(
            service_instance_name,
            service_plan_guid,
            space_guid,
            cluster_creation_parameters,
            poll_for_completion=False)

        cluster_instance_guid = response['metadata']['guid']

        return cluster_instance_guid
    #
    # operations on a specific cluster - requires cluster_instance_id
    #

    # TODO rename to cloud foundry status
    def status(self, cluster_instance_guid, poll_while_in_progress=False):
        if poll_while_in_progress:
            return self.cf_client.service_instances.poll_for_completion(
                cluster_instance_guid)
        else:
            status = self.cf_client.service_instances.status(
                service_instance_id=cluster_instance_guid)
            return status['entity']['last_operation']['state']

    def dataplatform_status(self, vcap):
        return self.dataplatform_api.status(vcap)

    def delete_cluster(self, cluster_instance_guid, recursive=False):
        try:
            self.cf_client.service_instances.delete_service_instance(
                service_instance_id=cluster_instance_guid, recursive=recursive)
        except CloudFoundryException as e:
            self.log.debug(e.message)
            raise

    def get_or_create_credentials(self, cluster_instance_guid,):

        get_sk_json = self.cf_client.service_keys.get_service_keys(
            service_instance_guid=cluster_instance_guid)

        if get_sk_json['total_results'] >= 1:
            # we found some credentials, so return the first set of credentials
            return get_sk_json['resources'][0]['entity']['credentials']
        else:
            status = self.status(cluster_instance_guid=cluster_instance_guid)
            if status != 'succeeded':
                raise RuntimeError("Cluster status is '{}' but must be 'succeeded' to create credentials.".format(status))

            # create some credentials and return them
            create_sk_json = self.cf_client.service_keys.create_service_key(cluster_instance_guid)
            return create_sk_json['entity']['credentials']

    def print_all_clusters(self):
        import pprint
        pp = pprint.PrettyPrinter(indent=4)

        for org in self.cf_client.orgs_and_spaces():
            for space in org['spaces']:
                print('ORG {} | SPACE {}'.format(org['name'], space['name']))
                print()

                clusters = self.clusters(space_guid=space['guid'])
                if len(clusters) > 0:
                    for cluster in clusters:
                        pp.pprint(cluster)
                        print()

class AmbariOperations:

    def __init__(self, vcap=None, vcap_filename=None):

        self.log = Logger().get_logger(self.__class__.__name__)

        assert (vcap is not None or vcap_filename is not None) \
           and (vcap is None or vcap_filename is None), \
                "You must only provide a vcap object OR vcap_filename parameter"

        if vcap_filename is not None:
            import json
            vcap = json.load(open(vcap_filename))

        try:
            self.USER         = vcap['cluster']['user']
            self.PASSWORD     = vcap['cluster']['password']
            self.AMBARI_URL   = vcap['cluster']['service_endpoints']['ambari_console']
            self.CLUSTER_ID   = vcap['cluster']['cluster_id']
        except KeyError as e:
            self.log.error("Couldn't parse vcap credential json - attribute {} not found.".format(str(e)))
            raise

        # ensure we are compatible with python 2 and 3
        try:
            from urllib.parse import urlparse
        except ImportError:
            from urlparse import urlparse

        url = urlparse(self.AMBARI_URL)

        self.HOST = url.hostname
        self.PORT = url.port
        self.PROTOCOL = url.scheme

        from ambariclient.client import Ambari
        self.ambari_client = Ambari(self.HOST, 
                                    port=self.PORT, 
                                    username=self.USER, 
                                    password=self.PASSWORD, 
                                    protocol=self.PROTOCOL)

    def get_namenode_hostname(self):

        # gets first cluster - there will only be one
        CLUSTER_NAME = self.ambari_client.clusters.next().cluster_name 

        namenode_hc = self.ambari_client \
                            .clusters(CLUSTER_NAME) \
                            .services('HDFS') \
                            .components('NAMENODE') \
                            .host_components

        namenode_host_name = [hc.host_name for hc in namenode_hc if hc.host_name][0]
        return namenode_host_name



import web
import re

import api_base
from armada_command.consul import kv
from armada_command.consul.consul import consul_query


class List(api_base.ApiCommand):
    @staticmethod
    def __create_dict_from_tags(tags):
        if not tags:
            return {}
        return dict((tag.split(':', 1) + [None])[:2] for tag in tags)

    def GET(self):
        try:
            get_args = web.input(local=False, microservice_name=None, env=None, app_id=None)
            filter_local = bool(get_args.local)
            filter_microservice_name = get_args.microservice_name
            filter_env = get_args.env
            filter_app_id = get_args.app_id

            if filter_local:
                local_microservices_ids = set(consul_query('agent/services').keys())

            if filter_microservice_name:
                microservices_names = [filter_microservice_name]
                if '*' in filter_microservice_name:
                    names = list(consul_query('catalog/services').keys())
                    microservices_names = self.__filter_names(filter_microservice_name, names)
            else:
                microservices_names = list(consul_query('catalog/services').keys())

            result = []

            for microservice_name in microservices_names:
                if microservice_name == 'consul':
                    continue

                query = 'health/service/{microservice_name}'.format(**locals())
                instances = consul_query(query)
                for instance in instances:
                    microservice_checks_statuses = set(check['Status'] for check in (instance['Checks'] or []))
                    microservice_computed_status = '-'
                    for possible_status in ['passing', 'warning', 'critical']:
                        if possible_status in microservice_checks_statuses:
                            microservice_computed_status = possible_status

                    microservice_ip = instance['Node']['Address']
                    microservice_port = str(instance['Service']['Port'])
                    microservice_id = instance['Service']['ID']
                    container_id = microservice_id.split(':')[0]
                    microservice_tags = instance['Service']['Tags'] or []
                    microservice_tags_dict = self.__create_dict_from_tags(microservice_tags)
                    microservice_tags_set = set(microservice_tags)

                    matches_env = (filter_env is None) or ('env:' + filter_env in microservice_tags_set)
                    matches_app_id = (filter_app_id is None) or ('app_id:' + filter_app_id in microservice_tags_set)

                    if matches_env and matches_app_id and (not filter_local or microservice_id in local_microservices_ids):
                        microservice_address = microservice_ip + ':' + microservice_port
                        try:
                            microservice_start_timestamp = kv.get("start_timestamp/" + container_id)
                        except:
                            microservice_start_timestamp = None
                        microservice_dict = {
                            'name': microservice_name,
                            'address': microservice_address,
                            'microservice_id': microservice_id,
                            'container_id': container_id,
                            'status': microservice_computed_status,
                            'tags': microservice_tags_dict,
                            'start_timestamp': microservice_start_timestamp,
                        }
                        result.append(microservice_dict)

            return self.status_ok({'result': result})
        except Exception as e:
            return self.status_exception("Cannot get the list of services.", e)

    @staticmethod
    def __filter_names(filter, names):
        expr = filter[1:-1]
        if filter[0] != '*':
            expr = '^' + filter[0:-1]
        elif filter[-1] != '*':
            expr = filter[1:] + '$'
        ce = re.compile(expr)
        service_names = []
        for i in names:
            if ce.search(i) is not None:
                service_names.append(i)
        return service_names

# -*- coding: utf8 -*-
import json
from django.conf import settings

from goodrain_web.base import BaseHttpClient, httplib2

import logging

logger = logging.getLogger('default')


class RegionServiceApi(BaseHttpClient):
    def __init__(self, *args, **kwargs):
        BaseHttpClient.__init__(self, *args, **kwargs)
        self.default_headers = {'Connection': 'keep-alive', 'Content-Type': 'application/json'}
        if settings.MODULES["RegionToken"]:
            self.default_headers.update({"Authorization": settings.REGION_TOKEN})
        self.region_map = {}
        region_service_infos = settings.REGION_SERVICE_API
        for region_service_info in region_service_infos:
            client_info = {"url": region_service_info["url"]}
            if 'proxy' in region_service_info and region_service_info.get('proxy_priority', False) is True:
                client_info['client'] = self.make_proxy_http(region_service_info)
            else:
                client_info['client'] = httplib2.Http(timeout=25)
            self.region_map[region_service_info["region_name"]] = client_info
    
    def make_proxy_http(self, region_service_info):
        proxy_info = region_service_info['proxy']
        if proxy_info['type'] == 'http':
            proxy_type = httplib2.socks.PROXY_TYPE_HTTP_NO_TUNNEL
        else:
            raise TypeError("unsupport type: %s" % proxy_info['type'])
        
        proxy = httplib2.ProxyInfo(proxy_type, proxy_info['host'], proxy_info['port'])
        client = httplib2.Http(proxy_info=proxy, timeout=25)
        return client
    
    def _request(self, *args, **kwargs):
        region = kwargs.get('region')
        client = self.region_map[region]['client']
        response, content = super(RegionServiceApi, self)._request(client=client, *args, **kwargs)
        return response, content
    
    def create_service(self, region, tenant, body):
        url = self.region_map[region]['url'] + "/v1/tenants/" + tenant + "/services"
        res, body = self._post(url, self.default_headers, body, region=region)
        return body
    
    def update_service(self, region, service_id, data):
        url = self.region_map[region]['url'] + "/v1/services/" + service_id
        res, body = self._put(url, self.default_headers, json.dumps(data), region=region)
        return res, body
    
    def build_service(self, region, service_id, body):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/build/"
        res, body = self._post(url, self.default_headers, body, region=region)
        return body
    
    def check_service_status(self, region, service_id):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/status/"
        res, body = self._post(url, self.default_headers, region=region)
        return body

    def get_service_status(self, region, service_id):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/status/"
        res, body = self._get(url, self.default_headers, region=region)
        return body

    def deploy(self, region, service_id, body):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/deploy/"
        res, body = self._post(url, self.default_headers, body, region=region)
        return body
    
    def restart(self, region, service_id, body):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/restart/"
        res, body = self._post(url, self.default_headers, body, region=region)
        return body
    
    def start(self, region, service_id, body):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/start/"
        res, body = self._post(url, self.default_headers, body, region=region)
        return res, body
    
    def stop(self, region, service_id, body):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/stop/"
        res, body = self._post(url, self.default_headers, body, region=region)
        return body
    
    def delete(self, region, service_id):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/delete/"
        res, body = self._delete(url, self.default_headers, region=region)
        return body
    
    def check_status(self, region, body):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/status/"
        res, body = self._post(url, self.default_headers, body, region=region)
        return body
    
    def get_log(self, region, service_id, body):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/log/"
        res, body = self._post(url, self.default_headers, body, region=region)
        return body
    
    def get_userlog(self, region, service_id):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/userlog/"
        res, body = self._post(url, self.default_headers, region=region)
        return body
    
    def get_compile_log(self, region, service_id, body):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/compile-log/"
        res, body = self._post(url, self.default_headers, body, region=region)
        return body
    
    def verticalUpgrade(self, region, service_id, body):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/vertical/"
        res, body = self._post(url, self.default_headers, body, region=region)
        return body
    
    def horizontalUpgrade(self, region, service_id, body):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/horizontal/"
        res, body = self._put(url, self.default_headers, body, region=region)
        return body
    
    def addUserDomain(self, region, body):
        url = self.region_map[region]['url'] + "/v1/lb/user-domains"
        res, body = self._post(url, self.default_headers, body, region=region)
        return body
    
    def deleteUserDomain(self, region, body):
        url = self.region_map[region]['url'] + "/v1/lb/delete-domains-rule"
        res, body = self._post(url, self.default_headers, body, region=region)
        return body
    
    def changeMemory(self, region, service_id, body):
        url = self.region_map[region]['url'] + "/v1/services/" + service_id + "/language"
        res, body = self._post(url, self.default_headers, body, region=region)
        return body
    
    def pause(self, region, tenant_id):
        url = self.region_map[region]['url'] + "/v1/tenants/" + tenant_id + "/pause"
        res, body = self._post(url, self.default_headers, region=region)
        return body
    
    def unpause(self, region, tenant_id):
        url = self.region_map[region]['url'] + "/v1/tenants/" + tenant_id + "/unpause"
        res, body = self._post(url, self.default_headers, region=region)
        return body
    
    def writeToRegionBeanstalk(self, region, service_id, body):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/beanstalk/"
        res, body = self._post(url, self.default_headers, body, region=region)
        return body
    
    def createServiceDependency(self, region, service_id, body):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/dependency/"
        res, body = self._post(url, self.default_headers, body, region=region)
        return body
    
    def cancelServiceDependency(self, region, service_id, body):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/dependency/"
        res, body = self._put(url, self.default_headers, body, region=region)
        return body

    def createL7Conf(self, region, service_id, body):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/l7_conf/"
        res, body = self._post(url, self.default_headers, body, region=region)
        return body

    def createServiceEnv(self, region, service_id, body):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/env-var/"
        logger.debug("api.region", "function: {0}, {1}".format('createServiceEnv', url))
        res, body = self._post(url, self.default_headers, body, region=region)
        return body
    
    def getTenantRunningServiceId(self, region, tenant_id):
        url = self.region_map[region]['url'] + "/v1/tenants/" + tenant_id + "/running-service"
        res, body = self._post(url, self.default_headers, region=region)
        return body
    
    def systemPause(self, region, tenant_id):
        url = self.region_map[region]['url'] + "/v1/tenants/" + tenant_id + "/system-pause"
        res, body = self._post(url, self.default_headers, region=region)
        return body
    
    def systemUnpause(self, region, tenant_id):
        url = self.region_map[region]['url'] + "/v1/tenants/" + tenant_id + "/system-unpause"
        res, body = self._post(url, self.default_headers, region=region)
        return body
    
    def findMappingPort(self, region, service_id):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/port-mapping/"
        res, body = self._get(url, self.default_headers, region=region)
        return body
    
    def bindingMappingPortIp(self, region, service_id, body):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/port-mapping/"
        res, body = self._put(url, self.default_headers, body, region=region)
        return body
    
    def manageServicePort(self, region, service_id, body):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/ports"
        res, body = self._post(url, self.default_headers, body, region=region)
        return body
    
    def opentsdbQuery(self, region, start, queries):
        url = self.region_map[region]['url'] + "/v1/statistic/opentsdb/query"
        data = {"start": start, "queries": queries}
        res, body = self._post(url, self.default_headers, json.dumps(data), region=region)
        try:
            dps = body[0]['dps']
            return dps
        except IndexError:
            logger.info('tsdb_query', "request: {0}".format(url))
            logger.info('tsdb_query', "response: {0} ====== {1}".format(res, body))
            return None
    
    def create_tenant(self, region, tenant_name, tenant_id):
        url = self.region_map[region]['url'] + '/v1/tenants'
        data = {"tenant_id": tenant_id, "tenant_name": tenant_name}
        res, body = self._post(url, self.default_headers, json.dumps(data), region=region)
        return res, body
    
    def getLatestServiceEvent(self, region, service_id):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/latest-event/"
        res, body = self._post(url, self.default_headers, region=region)
        return body
    
    def rollback(self, region, service_id, body):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/roll-back/"
        res, body = self._post(url, self.default_headers, body, region=region)
        return body
    
    def send_task(self, region, topic, body):
        url = self.region_map[region]['url'] + "/v1/queue?topic=" + topic
        res, body = self._post(url, self.default_headers, body, region=region)
        return body
    
    def create_event(self, region, body):
        url = self.region_map[region]['url'] + "/v1/events"
        res, body = self._post(url, self.default_headers, body, region=region)
        return body
    
    def history_log(self, region, service_id):
        url = self.region_map[region]['url'] + "/v1/statistic/log/" + service_id + "/list"
        res, body = self._get(url, self.default_headers, region=region)
        return body
    
    def latest_log(self, region, service_id, body):
        url = self.region_map[region]['url'] + "/v1/statistic/log/" + service_id + "/last"
        res, body = self._get(url, self.default_headers, body, region=region)
        return body
    
    def createServiceMnt(self, region, service_id, body):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/mnt/"
        res, body = self._post(url, self.default_headers, body, region=region)
        return body
    
    def cancelServiceMnt(self, region, service_id, body):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/mnt/"
        res, body = self._put(url, self.default_headers, body, region=region)
        return body
    
    def createServicePort(self, region, service_id, body):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/port-var/"
        res, body = self._post(url, self.default_headers, body, region=region)
        return body
    
    def extendMethodUpgrade(self, region, service_id, body):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/extend-method/"
        res, body = self._post(url, self.default_headers, body, region=region)
        return body
    
    def serviceContainerIds(self, region, service_id):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/containerIds/"
        res, body = self._post(url, self.default_headers, region=region)
        return body
    
    def createServiceVolume(self, region, service_id, body):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/volume/"
        res, body = self._post(url, self.default_headers, body, region=region)
        return res, body
    
    def cancelServiceVolume(self, region, service_id, body):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/volume/"
        res, body = self._put(url, self.default_headers, body, region=region)
        return res, body
    
    # 服务对外端口开启类型
    def mutiPortSupport(self, region, service_id, body):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/multi-outer-port/"
        res, body = self._post(url, self.default_headers, body, region=region)
        return res, body
    
    # 服务挂载卷类型
    def mntShareSupport(self, region, service_id, body):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/mnt-share-type/"
        res, body = self._post(url, self.default_headers, body, region=region)
        return res, body
    
    def tenantServiceStats(self, region, service_id):
        url = self.region_map[region]['url'] + "/v1/services/lifecycle/" + service_id + "/container-stats/"
        res, body = self._get(url, self.default_headers, region=region)
        return body
    
    def monitoryQueryMem(self, region, service_id):
        url = self.region_map[region]['url'] + "/v1/monitor/container/query/mem/" + service_id
        res, body = self._get(url, self.default_headers, region=region)
        return body
    
    def monitoryQueryCPU(self, region, service_id):
        url = self.region_map[region]['url'] + "/v1/monitor/container/query/cpu/" + service_id
        res, body = self._get(url, self.default_headers, region=region)
        return body
    
    def monitoryQueryFS(self, region, service_id):
        url = self.region_map[region]['url'] + "/v1/monitor/container/query/fs/" + service_id
        res, body = self._get(url, self.default_headers, region=region)
        return body
    
    def monitoryQueryIO(self, region, service_id):
        url = self.region_map[region]['url'] + "/v1/monitor/container/query/io/" + service_id
        res, body = self._get(url, self.default_headers, region=region)
        return body
    
    def getEventLog(self, region, event_id, level):
        url = self.region_map[region]['url'] + "/v1/event/" + event_id + "/log?level=" + level
        res, body = self._get(url, self.default_headers, region=region)
        return body
    
    def deleteEventLog(self, region, event_ids):
        url = self.region_map[region]['url'] + "/v1/events/log"
        res, body = self._delete(url, self.default_headers, body=event_ids,
                                 region=region)
        return body

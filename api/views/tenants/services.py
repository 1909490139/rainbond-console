# -*- coding: utf8 -*-
import time
import datetime
import json

from rest_framework.response import Response
from api.views.base import APIView
from www.models import TenantServiceStatics, Tenants, TenantRegionInfo, TenantServiceInfo, TenantServiceEnv, \
    ServiceEvent
from www.service_http import RegionServiceApi
from www.db import BaseConnection

import logging

logger = logging.getLogger('default')

regionClient = RegionServiceApi()


class TenantServiceStaticsView(APIView):
    '''
    计费基础数据统计
    '''
    allowed_methods = ('POST',)
    
    def post(self, request, format=None):
        """
        统计租户服务
        ---
        parameters:
            - name: data
              description: 数据列表
              required: true
              type: string
              paramType: body
        """
        datas = request.data
        beginTime = time.time()
        for data in datas:
            try:
                tenant_id = data["tenant_id"]
                service_id = data["service_id"]
                node_num = data["node_num"]
                node_memory = data["node_memory"]
                time_stamp = data["time_stamp"]
                storage_disk = data["storage_disk"]
                net_in = data["net_in"]
                net_out = data["net_out"]
                flow = data["flow"]
                region = data["region"]
                runing_status = data["status"]
                start_time = time.time()
                cnt = TenantServiceStatics.objects.filter(service_id=service_id, time_stamp=time_stamp).count()
                if cnt < 1:
                    ts = TenantServiceStatics(tenant_id=tenant_id, service_id=service_id, node_num=node_num,
                                              node_memory=node_memory,
                                              time_stamp=time_stamp, storage_disk=storage_disk, net_in=net_in,
                                              net_out=net_out, status=runing_status, flow=flow, region=region)
                    ts.save()
                end_time = time.time()
                logger.debug('statistic.perf', "sql execute time: {0}".format(end_time - start_time))
            except Exception as e:
                logger.exception(e)
            endTime = time.time()
            logger.debug('statistic.perf', "total use time: {0}".format(endTime - beginTime))
        return Response({"ok": True}, status=200)


class TenantHibernateView(APIView):
    '''
    租户休眠
    '''
    allowed_methods = ('put', 'post')
    
    def put(self, request, format=None):
        """
        休眠容器(pause,systemPause,unpause)
        ---
        parameters:
            - name: tenant_id
              description: 租户ID
              required: true
              type: string
              paramType: form
            - name: action
              description: 动作
              required: true
              type: string
              paramType: form
        """
        tenant_id = request.data.get('tenant_id', "")
        action = request.data.get('action', "")
        region = request.data.get('region', None)
        if region is None:
            return Response({"ok": False, "info": "need region field"}, status=400)
        
        logger.debug("tenant.pause", request.data)
        try:
            tenant = Tenants.objects.get(tenant_id=tenant_id)
            tenant_region = TenantRegionInfo.objects.get(tenant_id=tenant_id, region_name=region)
            if action == "pause":
                if tenant_region.service_status == 1:
                    regionClient.pause(region, tenant_region.tenant_id)
                    logger.info("tenant.pause", "tenant {0} paused at region {1}".format(tenant.tenant_name, region))
                    tenant_region.service_status = 0
                    tenant_region.save()
                else:
                    logger.debug("tenant.pause", tenant.tenant_name + " don't been paused")
            elif action == "systemPause":
                if tenant_region.service_status == 0:
                    regionClient.systemPause(region, tenant_region.tenant_id)
                    logger.info("tenant.pause",
                                "tenant {0} systemPaused at region {1}".format(tenant.tenant_name, region))
                    tenant_region.service_status = 3
                    tenant_region.save()
                else:
                    logger.debug("tenant.pause", tenant.tenant_name + " don't been paused")
            elif action == 'unpause':
                if tenant_region.service_status == 0:
                    regionClient.unpause(region, tenant_region.tenant_id)
                    logger.info("tenant.pause", "tenant {0} unpaused at region {1}".format(tenant.tenant_name, region))
                    tenant_region.service_status = 1
                    tenant_region.save()
                elif tenant_region.service_status == 3:
                    regionClient.systemUnpause(region, tenant_region.tenant_id)
                    logger.info("tenant.pause",
                                "tenant {0} systemunpaused at region {1}".format(tenant.tenant_name, region))
                    tenant_region.service_status = 1
                    tenant_region.save()
                else:
                    logger.debug("tenant.pause", tenant.tenant_name + " don't been unpaused")
            return Response({"ok": True}, status=200)
        except TenantRegionInfo.DoesNotExist:
            logger.error("tenant.pause", "object not find, region: {0}, tenant_id: {1}".format(region, tenant_id))
            return Response({"ok": False, "info": "region not found"}, status=400)
        except Exception, e:
            logger.exception("tenant.pause", e)
            return Response({"ok": False, "info": e.__str__()}, status=500)
    
    def post(self, request, format=None):
        """
        休眠容器(pause,unpause)
        ---
        parameters:
            - name: tenant_name
              description: 租户名
              required: true
              type: string
              paramType: form
            - name: action
              description: 动作
              required: true
              type: string
              paramType: form
        """
        tenant_name = request.data.get('tenant_name', "")
        action = request.data.get('action', "")
        region = request.data.get('region', None)
        if region is None:
            return Response({"ok": False, "info": "need region field"}, status=400)
        
        logger.debug("tenant.pause", request.data)
        try:
            tenant = Tenants.objects.get(tenant_name=tenant_name)
            tenant_region = TenantRegionInfo.objects.get(tenant_id=tenant.tenant_id, region_name=region)
            if action == "pause":
                if tenant_region.service_status == 1:
                    regionClient.pause(region, tenant_region.tenant_id)
                    logger.info("tenant.pause", "tenant {0} paused at region {1}".format(tenant.tenant_name, region))
                    tenant_region.service_status = 0
                    tenant_region.save()
                else:
                    logger.debug("tenant.pause", tenant_name + " don't been paused")
            elif action == "systemPause":
                if tenant_region.service_status == 0:
                    regionClient.systemPause(region, tenant_region.tenant_id)
                    logger.info("tenant.pause",
                                "tenant {0} systempaused at region {1}".format(tenant.tenant_name, region))
                    tenant_region.service_status = 3
                    tenant_region.save()
                else:
                    logger.debug("tenant.pause", tenant_name + " don't been paused")
            elif action == 'unpause':
                if tenant_region.service_status == 0:
                    regionClient.unpause(region, tenant_region.tenant_id)
                    logger.info("tenant.pause", "tenant {0} unpaused at region {1}".format(tenant.tenant_name, region))
                    tenant_region.service_status = 1
                    tenant_region.save()
                elif tenant_region.service_status == 3:
                    regionClient.systemUnpause(region, tenant_region.tenant_id)
                    logger.info("tenant.pause",
                                "tenant {0} systemunpaused at region {1}".format(tenant.tenant_name, region))
                    tenant_region.service_status = 1
                    tenant_region.save()
                else:
                    logger.debug("tenant.pause", tenant.tenant_name + " don't been unpaused")
        except Exception as e:
            logger.exception(e)
        return Response({"ok": True}, status=200)


class AllTenantView(APIView):
    '''
    租户信息
    '''
    allowed_methods = ('post',)
    
    def post(self, request, format=None):
        """
        获取所有租户信息
        ---
        parameters:
            - name: service_status
              description: 服务状态
              required: true
              type: string
              paramType: form
            - name: pay_type
              description: 租户类型
              required: true
              type: string
              paramType: form
            - name: region
              description: 区域中心
              required: true
              type: string
              paramType: form
            - name: day
              description: 相差天数
              required: false
              type: string
              paramType: form

        """
        service_status = request.data.get('service_status', "1")
        pay_type = request.data.get('pay_type', "free")
        region = request.data.get('region', "")
        query_day = request.data.get('day', "0")
        diff_day = int(query_day)
        data = {}
        try:
            if region != "":
                dsn = BaseConnection()
                query_sql = ""
                if diff_day != 0:
                    end_time = datetime.datetime.now() + datetime.timedelta(days=-1 * diff_day)
                    str_time = end_time.strftime("%Y-%m-%d %H:%M:%S")
                    query_sql = '''select ti.tenant_id,ti.tenant_name from tenant_info ti left join tenant_region tr on ti.tenant_id=tr.tenant_id where tr.is_init=1 and tr.service_status="{service_status}" and ti.pay_type="{pay_type}" and tr.region_name="{region}" and tr.update_time <= "{end_time}"
                        '''.format(service_status=service_status, pay_type=pay_type, region=region, end_time=str_time)
                else:
                    query_sql = '''select ti.tenant_id,ti.tenant_name from tenant_info ti left join tenant_region tr on ti.tenant_id=tr.tenant_id where tr.is_init=1 and tr.service_status="{service_status}" and ti.pay_type="{pay_type}" and tr.region_name="{region}"
                        '''.format(service_status=service_status, pay_type=pay_type, region=region)
                if query_sql != "":
                    sqlobjs = dsn.query(query_sql)
                    if sqlobjs is not None and len(sqlobjs) > 0:
                        for sqlobj in sqlobjs:
                            data[sqlobj['tenant_id']] = sqlobj['tenant_name']
        except Exception as e:
            logger.exception(e)
        return Response(data, status=200)


class TenantView(APIView):
    '''
    租户信息
    '''
    allowed_methods = ('post',)
    
    def post(self, request, format=None):
        """
        获取某个租户信息(tenant_id或者tenant_name)
        ---
        parameters:
            - name: tenant_id
              description: 租户ID
              required: false
              type: string
              paramType: form
            - name: tenant_name
              description: 租户名
              required: false
              type: string
              paramType: form

        """
        data = {}
        try:
            print request.data
            tenant_id = request.data.get('tenant_id', "")
            tenant_name = request.data.get('tenant_name', "")
            tenant = None
            if tenant_id != "":
                tenant = Tenants.objects.get(tenant_id=tenant_id)
            if tenant is None:
                if tenant_name != "":
                    tenant = Tenants.objects.get(tenant_name=tenant_name)
            if tenant is not None:
                data["tenant_id"] = tenant.tenant_id
                data["tenant_name"] = tenant.tenant_name
                tenantRegionList = TenantRegionInfo.objects.filter(tenant_id=tenant.tenant_id, is_active=True)
                regions = []
                for tenantRegion in tenantRegionList:
                    region_data = {}
                    region_data["region_name"] = tenantRegion.region_name
                    region_data["service_status"] = tenantRegion.service_status
                    regions.append(region_data)
                data["regions"] = regions
                data["pay_type"] = tenant.pay_type
        except Exception as e:
            logger.exception(e)
        return Response(data, status=200)


class GitCheckCodeView(APIView):
    def post(self, request, format=None):
        """
    代码检测
        ---
        parameters:
            - name: service_id
              description: 租户ID
              required: false
              type: string
              paramType: form
            - name: condition
              description: 检测条件
              required: false
              type: string
              paramType: form

    """
        data = {}
        try:
            service_id = request.data.get('service_id', "")
            dependency = request.data.get("condition", "")
            logger.debug(service_id + "=" + dependency)
            if service_id != "" and dependency != "":
                dps = json.loads(dependency)
                language = dps["language"]
                if language is not None and language != "" and language != "no":
                    try:
                        tse = TenantServiceEnv.objects.get(service_id=service_id)
                        tse.language = language
                        tse.check_dependency = dependency
                        tse.save()
                    except Exception:
                        tse = TenantServiceEnv(service_id=service_id, language=language, check_dependency=dependency)
                        tse.save()
                    service = TenantServiceInfo.objects.get(service_id=service_id)
                    if language != "false":
                        if language.find("Java") > -1 and service.min_memory < 512:
                            service.min_memory = 512
                            data = {}
                            data["language"] = "java"
                            regionClient.changeMemory(service.service_region, service_id, json.dumps(data))
                        service.language = language
                        service.save()
            data["status"] = "success"
        except Exception as e:
            logger.exception(e)
            data["status"] = "failure"
        return Response(data, status=200)


class UpdateServiceExpireTime(APIView):
    allowed_methods = ('put',)
    
    def put(self, request, format=None):
        """

        更新租户服务过期时间和最大内存
        ---
        parameters:
            - name: service_id
              description: 服务ID
              required: true
              type: string
              paramType: form
            - name: expired_days
              description: 剩余过期天数
              required: false
              type: int
              paramType: form

        """
        data = {}
        status = 200
        try:
            service_id = request.data.get("service_id", "")
            expired_days = request.data.get("expired_days", 7)
            service = TenantServiceInfo.objects.get(service_id=service_id)
            if expired_days.strip():
                if service.expired_time:
                    service.expired_time = service.expired_time + datetime.timedelta(days=int(expired_days))
                else:
                    service.expired_time = datetime.datetime.now() + datetime.timedelta(days=int(expired_days))
            service.save()
            data["status"] = "success"
        except TenantServiceInfo.DoesNotExist:
            logger.error("service_id :{0} is not found".format(service_id))
            data["status"] = "failure"
            status = 404
        except Exception as e:
            logger.exception(e)
            data["status"] = "failure"
            status = 500
        return Response(data, status=status)


class ServiceEventUpdate(APIView):
    allowed_methods = ('put',)
    
    def put(self, request, format=None):
        """

        更新服务操作状态
        ---
        parameters:
            - name: event_id
              description: 操作ID
              required: true
              type: string
              paramType: form
            - name: status
              description: 操作状态
              required: false
              type: string
              paramType: form
            - name: message
              description: 操作说明
              required: false
              type: string
              paramType: form
        """
        data = {}
        status = 200
        try:
            event_id = request.data.get("event_id", "")
            if not event_id:
                data["status"] = "failure"
                status = 404
                return Response(data, status=status)
            event_status = request.data.get("status", "failure")
            message = request.data.get("message", "")
            event = ServiceEvent.objects.get(event_id=event_id)
            if event:
                event.status = event_status
                event.final_status = "complete"
                event.message = message
                event.end_time = datetime.datetime.now()
                if event.status == "failure" and event.type == "callback":
                    event.deploy_version = event.old_deploy_version
                event.save()
                data["status"] = "success"
        
        except ServiceEvent.DoesNotExist:
            data["status"] = "failure"
            status = 404
        except Exception as e:
            logger.exception(e)
            logger.error("api", u"更新操作结果发生错误." + e.message)
            data["status"] = "failure"
            status = 500
        return Response(data, status=status)


class ServiceEventCodeVersionUpdate(APIView):
    allowed_methods = ('put',)
    
    def put(self, request, format=None):
        """

        更新服务操作状态
        ---
        parameters:
            - name: event_id
              description: 操作ID
              required: true
              type: string
              paramType: form
            - name: code_version
              description: 代码版本
              required: false
              type: string
              paramType: form
        """
        data = {}
        status = 200
        try:
            event_id = request.data.get("event_id", "")
            if not event_id:
                data["status"] = "failure"
                status = 404
                return Response(data, status=status)
            code_version = request.data.get("code_version", "")
            event = ServiceEvent.objects.get(event_id=event_id)
            if event:
                event.code_version = code_version
                event.save()
                data["status"] = "success"
        except ServiceEvent.DoesNotExist:
            data["status"] = "failure"
            status = 404
        except Exception as e:
            logger.exception(e)
            logger.error("api", u"更新操作结果发生错误." + e.message)
            data["status"] = "failure"
            status = 500
        return Response(data, status=status)

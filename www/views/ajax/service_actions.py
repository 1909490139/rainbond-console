# -*- coding: utf8 -*-
import datetime
import json
import re

from django.http import JsonResponse

from www.models.main import ServiceGroupRelation, ServiceAttachInfo, ServiceCreateStep, ServiceFeeBill, ServiceConsume
from www.views import AuthedView
from www.decorator import perm_required

from www.models import (ServiceInfo, AppService, TenantServiceInfo,
                        TenantRegionInfo, PermRelService, TenantServiceRelation,
                        TenantServiceInfoDelete, Users, TenantServiceEnv,
                        TenantServiceAuth, ServiceDomain, TenantServiceEnvVar,
                        TenantServicesPort, TenantServiceMountRelation, TenantServiceVolume, ServiceEvent, TenantServiceL7Info)

from www.service_http import RegionServiceApi
from django.conf import settings
from www.tenantservice.baseservice import BaseTenantService, TenantUsedResource, TenantAccountService, \
    CodeRepositoriesService
from goodrain_web.decorator import method_perf_time
from www.monitorservice.monitorhook import MonitorHook
from www.utils.giturlparse import parse as git_url_parse
from www.forms.services import EnvCheckForm

import logging
from www.utils.crypt import make_uuid

logger = logging.getLogger('default')

regionClient = RegionServiceApi()
baseService = BaseTenantService()
tenantUsedResource = TenantUsedResource()
monitorhook = MonitorHook()
tenantAccountService = TenantAccountService()
codeRepositoriesService = CodeRepositoriesService()


class AppDeploy(AuthedView):
    def _saveAdapterEnv(self, service):
        num = TenantServiceEnvVar.objects.filter(service_id=service.service_id, attr_name="GD_ADAPTER").count()
        if num < 1:
            attr = {"tenant_id": service.tenant_id, "service_id": service.service_id, "name": "GD_ADAPTER",
                    "attr_name": "GD_ADAPTER", "attr_value": "true", "is_change": 0, "scope": "inner",
                    "container_port": -1}
            TenantServiceEnvVar.objects.create(**attr)
            data = {"action": "add", "attrs": attr}
            regionClient.createServiceEnv(service.service_region, service.service_id, json.dumps(data))
    
    @method_perf_time
    @perm_required('code_deploy')
    def post(self, request, *args, **kwargs):
        data = {}
        if 'event_id' not in request.POST:
            data["status"] = "failure"
            data["message"] = "event is not exist."
            return JsonResponse(data, status=412)
        event_id = request.POST["event_id"]
        event = ServiceEvent.objects.get(event_id=event_id)
        
        if not event:
            data["status"] = "failure"
            data["message"] = "event is not exist."
            return JsonResponse(data, status=412)
        
        if tenantAccountService.isOwnedMoney(self.tenant, self.service.service_region):
            data["status"] = "owed"
            return JsonResponse(data, status=200)
        
        if tenantAccountService.isExpired(self.tenant, self.service):
            data["status"] = "expired"
            return JsonResponse(data, status=200)
        
        if self.service.language is None or self.service.language == "":
            data["status"] = "language"
            return JsonResponse(data, status=200)
        
        tenant_id = self.tenant.tenant_id
        service_id = self.service.service_id
        
        # oldVerion = self.service.deploy_version
        # if oldVerion is not None and oldVerion != "":
        #     if not baseService.is_user_click(self.service.service_region, service_id):
        #         data["status"] = "often"
        #         return JsonResponse(data, status=200)
        
        # calculate resource
        rt_type, flag = tenantUsedResource.predict_next_memory(self.tenant, self.service, 0, True)
        if not flag:
            if rt_type == "memory":
                data["status"] = "over_memory"
            else:
                data["status"] = "over_money"
            return JsonResponse(data, status=200)
        
        # if docker set adapter env
        if self.service.language == "docker":
            self._saveAdapterEnv(self.service)
        
        try:
            gitUrl = request.POST.get('git_url', None)
            if gitUrl is None:
                gitUrl = self.service.git_url
            body = {}
            if self.service.deploy_version == "" or self.service.deploy_version is None:
                body["action"] = "deploy"
            else:
                body["action"] = "upgrade"
            
            self.service.deploy_version = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
            self.service.save()
            
            # 保存最新 deploy_version
            event.deploy_version = self.service.deploy_version
            event.save()
            
            clone_url = self.service.git_url
            if self.service.code_from == "github":
                code_user = clone_url.split("/")[3]
                code_project_name = clone_url.split("/")[4].split(".")[0]
                createUser = Users.objects.get(user_id=self.service.creater)
                clone_url = "https://" + createUser.github_token + "@github.com/" + code_user + "/" + code_project_name + ".git"
            body["deploy_version"] = self.service.deploy_version
            body["gitUrl"] = "--branch " + self.service.code_version + " --depth 1 " + clone_url
            body["operator"] = str(self.user.nick_name)
            body["event_id"] = event_id
            envs = {}
            buildEnvs = TenantServiceEnvVar.objects.filter(service_id=service_id, attr_name__in=(
                "COMPILE_ENV", "NO_CACHE", "DEBUG", "PROXY", "SBT_EXTRAS_OPTS"))
            for benv in buildEnvs:
                envs[benv.attr_name] = benv.attr_value
            body["envs"] = json.dumps(envs)
            
            regionClient.build_service(self.service.service_region, service_id, json.dumps(body))
            monitorhook.serviceMonitor(self.user.nick_name, self.service, 'app_deploy', True)
            
            data["status"] = "success"
            return JsonResponse(data, status=200)
        except Exception as e:
            logger.exception(e)
            data["status"] = "failure"
            monitorhook.serviceMonitor(self.user.nick_name, self.service, 'app_deploy', False)
        return JsonResponse(data, status=500)


class ServiceManage(AuthedView):
    @perm_required('manage_service')
    def post(self, request, *args, **kwargs):
        result = {}
        
        if 'event_id' not in request.POST:
            result["status"] = "failure"
            result["message"] = "event is not exist."
            return JsonResponse(result, status=412)
        event_id = request.POST["event_id"]
        event = ServiceEvent.objects.get(event_id=event_id)
        if not event:
            result["status"] = "failure"
            result["message"] = "event is not exist."
            return JsonResponse(result, status=412)
        event.deploy_version = self.service.deploy_version
        
        action = request.POST["action"]
        user_actions = ("rollback", "restart", "reboot")
        if action in user_actions:
            if tenantAccountService.isOwnedMoney(self.tenant, self.service.service_region):
                result["status"] = "owed"
                self.update_event(event, "余额不足请及时充值", "failure")
                return JsonResponse(result, status=200)
            
            if tenantAccountService.isExpired(self.tenant, self.service):
                result["status"] = "expired"
                self.update_event(event, "试用已到期", "failure")
                return JsonResponse(result, status=200)
        
        if action == "stop":
            try:
                body = {}
                body["operator"] = str(self.user.nick_name)
                body["event_id"] = event_id
                regionClient.stop(self.service.service_region, self.service.service_id, json.dumps(body))
                monitorhook.serviceMonitor(self.user.nick_name, self.service, 'app_stop', True)
                result["status"] = "success"
            except Exception, e:
                if event:
                    event.message = u"停止应用失败" + e.message
                    event.final_status = "complete"
                    event.status = "failure"
                    event.save()
                logger.exception(e)
                result["status"] = "failure"
                monitorhook.serviceMonitor(self.user.nick_name, self.service, 'app_stop', False)
        elif action == "restart":
            try:
                # calculate resource
                diff_memory = self.service.min_node * self.service.min_memory
                rt_type, flag = tenantUsedResource.predict_next_memory(self.tenant, self.service, diff_memory, False)
                if not flag:
                    if rt_type == "memory":
                        result["status"] = "over_memory"
                        self.update_event(event, "资源已达上限，不能升级", "failure")
                    else:
                        result["status"] = "over_money"
                        self.update_event(event, "余额不足，不能升级", "failure")
                    return JsonResponse(result, status=200)
                body = {}
                body["deploy_version"] = self.service.deploy_version
                body["operator"] = str(self.user.nick_name)
                body["event_id"] = event_id
                regionClient.restart(self.service.service_region, self.service.service_id, json.dumps(body))
                monitorhook.serviceMonitor(self.user.nick_name, self.service, 'app_start', True)
                result["status"] = "success"
            except Exception, e:
                if event:
                    event.message = u"启动应用失败" + e.message
                    event.final_status = "complete"
                    event.status = "failure"
                    event.save()
                logger.exception(e)
                result["status"] = "failure"
                monitorhook.serviceMonitor(self.user.nick_name, self.service, 'app_start', False)
        elif action == "reboot":
            try:
                diff_memory = self.service.min_node * self.service.min_memory
                rt_type, flag = tenantUsedResource.predict_next_memory(self.tenant, self.service, diff_memory, False)
                if not flag:
                    if rt_type == "memory":
                        result["status"] = "over_memory"
                        self.update_event(event, "资源不足，不能升级", "failure")
                    else:
                        result["status"] = "over_money"
                        self.update_event(event, "余额不足，不能升级", "failure")
                    return JsonResponse(result, status=200)
                # stop service
                body = {}
                body["operator"] = str(self.user.nick_name)
                body["event_id"] = event_id
                regionClient.stop(self.service.service_region, self.service.service_id, json.dumps(body))
                monitorhook.serviceMonitor(self.user.nick_name, self.service, 'app_stop', True)
                
                # start service
                body = {}
                body["deploy_version"] = self.service.deploy_version
                body["operator"] = str(self.user.nick_name)
                regionClient.restart(self.service.service_region, self.service.service_id, json.dumps(body))
                monitorhook.serviceMonitor(self.user.nick_name, self.service, 'app_start', True)
                
                result["status"] = "success"
            except Exception, e:
                if event:
                    event.message = u"重启应用失败" + e.message
                    event.final_status = "complete"
                    event.status = "failure"
                    event.save()
                logger.exception(e)
                result["status"] = "failure"
                monitorhook.serviceMonitor(self.user.nick_name, self.service, 'app_reboot', False)
        elif action == "delete":
            try:
                now = datetime.datetime.now()
                service_attach_info = ServiceAttachInfo.objects.get(service_id=self.service.service_id,
                                                                    tenant_id=self.tenant.tenant_id)
                has_prepaid_items = False
                if service_attach_info.memory_pay_method == "prepaid" or service_attach_info.disk_pay_method == "prepaid":
                    has_prepaid_items = True
                unpayed_bills = ServiceFeeBill.objects.filter(service_id=self.service.service_id,
                                                              tenant_id=self.tenant.tenant_id, pay_status="unpayed")
                if has_prepaid_items:
                    if now < service_attach_info.buy_end_time:
                        #  开始计费之前,如果已经付款
                        if not unpayed_bills:
                            result["status"] = "payed"
                            result["info"] = u"已付款应用无法删除"
                            self.update_event(event, "已付款应用无法删除", "failure")
                            return JsonResponse(result)
                
                published = AppService.objects.filter(service_id=self.service.service_id).count()
                if published:
                    result["status"] = "published"
                    self.update_event(event, "关联了已发布服务, 不可删除", "failure")
                    result["info"] = u"关联了已发布服务, 不可删除"
                    return JsonResponse(result)
                
                dependSids = TenantServiceRelation.objects.filter(dep_service_id=self.service.service_id).values(
                    "service_id")
                if len(dependSids) > 0:
                    sids = []
                    for ds in dependSids:
                        sids.append(ds["service_id"])
                    if len(sids) > 0:
                        aliasList = TenantServiceInfo.objects.filter(service_id__in=sids).values('service_cname')
                        depalias = ""
                        for alias in aliasList:
                            if depalias != "":
                                depalias = depalias + ","
                            depalias = depalias + alias["service_cname"]
                        result["dep_service"] = depalias
                        result["status"] = "evn_dependency"
                        self.update_event(event, "被依赖, 不可删除", "failure")
                        return JsonResponse(result)
                
                dependSids = TenantServiceMountRelation.objects.filter(dep_service_id=self.service.service_id).values(
                    "service_id")
                if len(dependSids) > 0:
                    sids = []
                    for ds in dependSids:
                        sids.append(ds["service_id"])
                    if len(sids) > 0:
                        aliasList = TenantServiceInfo.objects.filter(service_id__in=sids).values('service_alias')
                        depalias = ""
                        for alias in aliasList:
                            if depalias != "":
                                depalias = depalias + ","
                            depalias = depalias + alias["service_alias"]
                        result["dep_service"] = depalias
                        result["status"] = "mnt_dependency"
                        self.update_event(event, "被依赖, 不可删除", "failure")
                        return JsonResponse(result)
                
                data = self.service.toJSON()
                newTenantServiceDelete = TenantServiceInfoDelete(**data)
                newTenantServiceDelete.save()
                try:
                    regionClient.delete(self.service.service_region, self.service.service_id)
                except Exception as e:
                    logger.exception(e)
                if self.service.code_from == 'gitlab_new' and self.service.git_project_id > 0:
                    codeRepositoriesService.deleteProject(self.service)
                
                TenantServiceInfo.objects.get(service_id=self.service.service_id).delete()
                # env/auth/domain/relationship/envVar/volume delete
                TenantServiceEnv.objects.filter(service_id=self.service.service_id).delete()
                TenantServiceAuth.objects.filter(service_id=self.service.service_id).delete()
                ServiceDomain.objects.filter(service_id=self.service.service_id).delete()
                TenantServiceRelation.objects.filter(service_id=self.service.service_id).delete()
                TenantServiceEnvVar.objects.filter(service_id=self.service.service_id).delete()
                TenantServiceMountRelation.objects.filter(service_id=self.service.service_id).delete()
                TenantServicesPort.objects.filter(service_id=self.service.service_id).delete()
                TenantServiceVolume.objects.filter(service_id=self.service.service_id).delete()
                ServiceGroupRelation.objects.filter(service_id=self.service.service_id,
                                                    tenant_id=self.tenant.tenant_id).delete()
                ServiceAttachInfo.objects.filter(service_id=self.service.service_id).delete()
                ServiceCreateStep.objects.filter(service_id=self.service.service_id).delete()
                
                events = ServiceEvent.objects.filter(service_id=self.service.service_id)
                deleteEventID = []
                if events:
                    for event in events:
                        deleteEventID.append(event.event_id)
                if len(deleteEventID) > 0:
                    regionClient.deleteEventLog(self.service.service_region,
                                                json.dumps({"event_ids": deleteEventID}))
                
                ServiceEvent.objects.filter(service_id=self.service.service_id).delete()
                
                monitorhook.serviceMonitor(self.user.nick_name, self.service, 'app_delete', True)
                result["status"] = "success"
            except Exception, e:
                if event:
                    event.message = u"删除应用失败" + e.message
                    event.final_status = "complete"
                    event.status = "failure"
                    event.save()
                logger.exception(e)
                result["status"] = "failure"
                monitorhook.serviceMonitor(self.user.nick_name, self.service, 'app_delete', False)
        elif action == "rollback":
            try:
                deploy_version = request.POST["deploy_version"]
                if event_id != "":
                    # calculate resource
                    rt_type, flag = tenantUsedResource.predict_next_memory(self.tenant, self.service, 0, True)
                    if not flag:
                        if rt_type == "memory":
                            result["status"] = "over_memory"
                            self.update_event(event, "资源不足，不能升级", "failure")
                        else:
                            result["status"] = "over_money"
                            self.update_event(event, "余额不足，不能升级", "failure")
                        return JsonResponse(result, status=200)
                    body = {}
                    body["event_id"] = event_id
                    body["operator"] = str(self.user.nick_name)
                    body["deploy_version"] = deploy_version
                    regionClient.rollback(self.service.service_region, self.service.service_id, json.dumps(body))
                    monitorhook.serviceMonitor(self.user.nick_name, self.service, 'app_rollback', True)
                result["status"] = "success"
                event.deploy_version = deploy_version
                event.save()
            except Exception, e:
                if event:
                    event.message = u"回滚应用失败" + e.message
                    event.final_status = "complete"
                    event.status = "failure"
                    event.save()
                logger.exception(e)
                result["status"] = "failure"
                monitorhook.serviceMonitor(self.user.nick_name, self.service, 'app_rollback', False)
        return JsonResponse(result)
    
    def update_event(self, event, message, status):
        event.status = status
        event.final_status = "complete"
        event.message = message
        event.end_time = datetime.datetime.now()
        if event.status == "failure" and event.type == "callback":
            event.deploy_version = event.old_deploy_version
        event.save()


class ServiceUpgrade(AuthedView):
    @perm_required('manage_service')
    def post(self, request, *args, **kwargs):
        result = {}
        if 'event_id' not in request.POST:
            result["status"] = "failure"
            result["message"] = "event is not exist."
            return JsonResponse(result, status=412)
        event_id = request.POST["event_id"]
        event = ServiceEvent.objects.get(event_id=event_id)
        if not event:
            result["status"] = "failure"
            result["message"] = "event is not exist."
            return JsonResponse(result, status=412)
        
        if tenantAccountService.isOwnedMoney(self.tenant, self.service.service_region):
            result["status"] = "owed"
            return JsonResponse(result, status=200)
        
        if tenantAccountService.isExpired(self.tenant, self.service):
            result["status"] = "expired"
            return JsonResponse(result, status=200)
        
        action = request.POST["action"]
        try:
            if action == "vertical":
                container_memory = request.POST["memory"]
                container_cpu = request.POST["cpu"]
                old_container_cpu = self.service.min_cpu
                old_container_memory = self.service.min_memory
                if int(container_memory) != old_container_memory or int(container_cpu) != old_container_cpu:
                    upgrade_container_memory = int(container_memory)
                    left = upgrade_container_memory % 128
                    if upgrade_container_memory > 0 and upgrade_container_memory <= 65536 and left == 0:
                        # calculate resource
                        diff_memory = upgrade_container_memory - int(old_container_memory)
                        rt_type, flag = tenantUsedResource.predict_next_memory(self.tenant, self.service, diff_memory,
                                                                               True)
                        if not flag:
                            if rt_type == "memory":
                                result["status"] = "over_memory"
                            else:
                                result["status"] = "over_money"
                            return JsonResponse(result, status=200)
                        
                        upgrade_container_cpu = upgrade_container_memory / 128 * 20
                        
                        body = {}
                        body["container_memory"] = upgrade_container_memory
                        body["deploy_version"] = self.service.deploy_version
                        body["container_cpu"] = upgrade_container_cpu
                        body["operator"] = str(self.user.nick_name)
                        body["event_id"] = event_id
                        regionClient.verticalUpgrade(self.service.service_region, self.service.service_id,
                                                     json.dumps(body))
                        
                        self.service.min_cpu = upgrade_container_cpu
                        self.service.min_memory = upgrade_container_memory
                        self.service.save()
                        
                        monitorhook.serviceMonitor(self.user.nick_name, self.service, 'app_vertical', True)
                result["status"] = "success"
            elif action == "horizontal":
                node_num = request.POST["node_num"]
                new_node_num = int(node_num)
                old_min_node = self.service.min_node
                if new_node_num >= 0 and new_node_num != old_min_node:
                    # calculate resource
                    diff_memory = (new_node_num - old_min_node) * self.service.min_memory
                    rt_type, flag = tenantUsedResource.predict_next_memory(self.tenant, self.service, diff_memory, True)
                    if not flag:
                        if rt_type == "memory":
                            result["status"] = "over_memory"
                        else:
                            result["status"] = "over_money"
                        return JsonResponse(result, status=200)
                    
                    body = {}
                    body["node_num"] = new_node_num
                    body["deploy_version"] = self.service.deploy_version
                    body["operator"] = str(self.user.nick_name)
                    body["event_id"] = event_id
                    regionClient.horizontalUpgrade(self.service.service_region, self.service.service_id,
                                                   json.dumps(body))
                    
                    self.service.min_node = new_node_num
                    self.service.save()
                    monitorhook.serviceMonitor(self.user.nick_name, self.service, 'app_horizontal', True)
                result["status"] = "success"
            elif action == "extend_method":
                extend_method = request.POST["extend_method"]
                if self.service.category == "application":
                    body = {}
                    body["extend_method"] = extend_method
                    body["event_id"] = event_id
                    regionClient.extendMethodUpgrade(self.service.service_region, self.service.service_id,
                                                     json.dumps(body))
                    self.service.extend_method = extend_method
                    self.service.save()
                    result["status"] = "success"
                else:
                    result["status"] = "no_support"
            elif action == "imageUpgrade":
                baseservice = ServiceInfo.objects.get(service_key=self.service.service_key,
                                                      version=self.service.version)
                if baseservice.update_version != self.service.update_version:
                    regionClient.update_service(self.service.service_region, self.service.service_id,
                                                {"image": baseservice.image})
                    self.service.image = baseservice.image
                    self.service.update_version = baseservice.update_version
                    self.service.save()
                result["status"] = "success"
        except Exception, e:
            logger.exception(e)
            if action == "vertical":
                monitorhook.serviceMonitor(self.user.nick_name, self.service, 'app_vertical', False)
            elif action == "horizontal":
                monitorhook.serviceMonitor(self.user.nick_name, self.service, 'app_horizontal', False)
            result["status"] = "failure"
        return JsonResponse(result)


class ServiceRelation(AuthedView):
    @perm_required('manage_service')
    def post(self, request, *args, **kwargs):
        result = {}
        action = request.POST["action"]
        dep_service_alias = request.POST["dep_service_alias"]
        try:
            tenant_id = self.tenant.tenant_id
            service_id = self.service.service_id
            tenantS = TenantServiceInfo.objects.get(tenant_id=tenant_id, service_alias=dep_service_alias)
            if action == "add":
                baseService.create_service_dependency(tenant_id, service_id, tenantS.service_id,
                                                      self.service.service_region)
                self.saveAdapterEnv(self.service)
            elif action == "cancel":
                baseService.cancel_service_dependency(tenant_id, service_id, tenantS.service_id,
                                                      self.service.service_region)
            result["status"] = "success"
        except Exception, e:
            logger.exception(e)
            result["status"] = "failure"
        return JsonResponse(result)
    
    def saveAdapterEnv(self, service):
        num = TenantServiceEnvVar.objects.filter(service_id=service.service_id, attr_name="GD_ADAPTER").count()
        if num < 1:
            attr = {"tenant_id": service.tenant_id, "service_id": service.service_id, "name": "GD_ADAPTER",
                    "attr_name": "GD_ADAPTER", "attr_value": "true", "is_change": 0, "scope": "inner",
                    "container_port": -1}
            TenantServiceEnvVar.objects.create(**attr)
            data = {"action": "add", "attrs": attr}
            regionClient.createServiceEnv(service.service_region, service.service_id, json.dumps(data))

class NoneParmsError(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)

class UseMidRain(AuthedView):
    @perm_required('manage_service')
    def post(self, request, *args, **kwargs):
        result = {}
        action = request.POST.get("action", None)
        try:
            if not action:
                raise NoneParmsError("UseMidRain need action.")
            if action == "add":
                self.saveAdapterEnv(self.service)
                self.addSevenLevelEnv(self.service)
                self.addIsHttpEnv(self.service)
            elif action == "del":
                self.delSevenLevelEnv(self.service)
            elif action == "check":
                if self.checkSevenLevelEnv(self.service):
                    result["is_mid"] = "no"
                else:
                    result["is_mid"] = "yes"

            result["status"] = "success"
        except Exception, e:
            logger.exception(e)
            result["status"] = "failure"
        return JsonResponse(result)

    def checkSevenLevelEnv(self, service):
        num = TenantServiceEnvVar.objects.filter(service_id=service.service_id, attr_name="SEVEN_LEVEL").count()
        if num < 1:
            return 1
        else:
            return 0

    def addSevenLevelEnv(self, service):
        num = TenantServiceEnvVar.objects.filter(service_id=service.service_id, attr_name="SEVEN_LEVEL").count()
        if num < 1:
            attr = {"tenant_id": service.tenant_id, "service_id": service.service_id, "name": "SEVEN_LEVEL",
                    "attr_name": "SEVEN_LEVEL", "attr_value": "true", "is_change": 0, "scope": "inner", "container_port":-1}
            TenantServiceEnvVar.objects.create(**attr)
            data = {"action": "add", "attrs": attr}
            regionClient.createServiceEnv(service.service_region, service.service_id, json.dumps(data))

    def addIsHttpEnv(self, service):
        # add domposer-compose
        is_compose = TenantServiceInfo.objects.filter(service_id=self.service.service_id, language="docker-compose")
        if is_compose:
            num = TenantServiceEnvVar.objects.filter(service_id=service.service_id, attr_name="IS_HTTP").count()
            if num < 1:
                attr = {"tenant_id": service.tenant_id, "service_id": service.service_id, "name": "IS_HTTP",
                        "attr_name": "IS_HTTP", "attr_value": "true", "is_change": 0, "scope": "inner", "container_port":-1}
                TenantServiceEnvVar.objects.create(**attr)
                data = {"action": "add", "attrs": attr}
                regionClient.createServiceEnv(service.service_region, service.service_id, json.dumps(data))
        else:
            pass

    def delSevenLevelEnv(self, service):
        num = TenantServiceEnvVar.objects.filter(service_id=service.service_id, attr_name="SEVEN_LEVEL").count()
        if num > 0:
            TenantServiceEnvVar.objects.get(service_id=service.service_id, attr_name="SEVEN_LEVEL").delete()
            data = {"action": "delete", "attr_names": ["SEVEN_LEVEL"]}
            regionClient.createServiceEnv(service.service_region, service.service_id, json.dumps(data))

    def saveAdapterEnv(self, service):
        num = TenantServiceEnvVar.objects.filter(service_id=service.service_id, attr_name="GD_ADAPTER").count()
        if num < 1:
            attr = {"tenant_id": service.tenant_id, "service_id": service.service_id, "name": "GD_ADAPTER",
                    "attr_name": "GD_ADAPTER", "attr_value": "true", "is_change": 0, "scope": "inner", "container_port":-1}
            TenantServiceEnvVar.objects.create(**attr)
            data = {"action": "add", "attrs": attr}
            regionClient.createServiceEnv(service.service_region, service.service_id, json.dumps(data))

class L7ServiceSet(AuthedView):
    @perm_required('manage_service')
    def post(self, request, *args, **kwargs):
        self.l7_json = request.POST["l7_json"]
        logger.debug("l7_json %s" % str(self.l7_json))
        self.dep_service_id = request.POST["dep_service_id"]
        result = {}
        try:
            self.addL7Info(self.service)
            result["status"] = "success"
        except Exception, e:
            logger.exception(e)
            result["status"] = "failure"
        return JsonResponse(result)

    def addL7Info(self, service):

        attr_l7 = {
            "tenant_id": self.service.tenant_id,
            "service_id": self.service.service_id,
            "dep_service_id": self.dep_service_id,
            "l7_json": self.l7_json
        }

        num = TenantServiceL7Info.objects.filter(service_id=service.service_id, dep_service_id=self.dep_service_id).count()
        if num < 1:
            TenantServiceL7Info.objects.create(**attr_l7)
            data = {"action": "add", "attrs": attr_l7}
            logger.debug("addL7Info num < 1 %s" % data)
            regionClient.createL7Conf(service.service_region, service.service_id, json.dumps(data))
        elif num == 1:
            TenantServiceL7Info.objects.filter(service_id=service.service_id, dep_service_id=self.dep_service_id).update(l7_json=self.l7_json)
            data = {"action": "update", "attrs": attr_l7}
            logger.debug("addL7Info num > 1 %s" % data)
            regionClient.createL7Conf(service.service_region, service.service_id, json.dumps(data))

    @perm_required('manage_service')
    def get(self, request, *args, **kwargs):
        result = {
            'cricuit':'1024',
            'domain':'off'
        }
        self.dep_service_id = request.GET.get("dep_service_id", None)
        try:
            if not self.dep_service_id:
                raise NoneParmsError("L7ServiceSet function get dep_service_id is None.")
            tsrlist = TenantServiceL7Info.objects.filter(service_id=self.service.service_id, dep_service_id=self.dep_service_id)
            if tsrlist:
                result = eval(tsrlist[0].l7_json)
                # 兼容
                if not result.get('domain', None):
                    result['domain'] = 'off'
            is_compose = TenantServiceInfo.objects.filter(service_id=self.service.service_id, language="docker-compose")
            if not is_compose:
                result["domain"] = "close"
            logger.debug("level7query is %s" % result)
        except Exception, e:
            logger.exception(e)
            return JsonResponse(result)

        return JsonResponse(result)


class AllServiceInfo(AuthedView):
    def init_request(self, *args, **kwargs):
        self.cookie_region = self.request.COOKIES.get('region')
        self.tenant_region = TenantRegionInfo.objects.get(tenant_id=self.tenant.tenant_id,
                                                          region_name=self.cookie_region)
    
    @method_perf_time
    @perm_required('tenant.tenant_access')
    def get(self, request, *args, **kwargs):
        result = {}
        service_ids = []
        try:
            tmp = TenantServiceInfo()
            if hasattr(tmp, 'service_origin'):
                service_list = TenantServiceInfo.objects.filter(
                    tenant_id=self.tenant.tenant_id,
                    service_region=self.cookie_region,
                    service_origin='assistant').values('ID', 'service_id', 'deploy_version')
            else:
                service_list = TenantServiceInfo.objects.filter(
                    tenant_id=self.tenant.tenant_id,
                    service_region=self.cookie_region).values('ID', 'service_id', 'deploy_version')
            if self.has_perm('tenant.list_all_services'):
                for s in service_list:
                    if s['deploy_version'] is None or s['deploy_version'] == "":
                        child1 = {}
                        child1["status"] = "undeploy"
                        result[s['service_id']] = child1
                    else:
                        service_ids.append(s['service_id'])
            else:
                service_pk_list = PermRelService.objects.filter(user_id=self.user.pk).values_list('service_id',
                                                                                                  flat=True)
                for s in service_list:
                    if s['ID'] in service_pk_list:
                        if s['deploy_version'] is None or s['deploy_version'] == "":
                            child1 = {}
                            child1["status"] = "undeploy"
                            result[s.service_id] = child1
                        else:
                            service_ids.append(s['service_id'])
            if len(service_ids) > 0:
                if self.tenant_region.service_status == 2 and self.tenant.pay_type == "payed":
                    for sid in service_ids:
                        child = {}
                        child["status"] = "owed"
                        result[sid] = child
                else:
                    id_string = ','.join(service_ids)
                    bodys = regionClient.check_status(self.cookie_region, json.dumps({"service_ids": id_string}))
                    # logger.debug(bodys)
                    for key, value in bodys.items():
                        child = {}
                        child["status"] = value
                        result[key] = child
        except Exception:
            tempIds = ','.join(service_ids)
            logger.debug(self.tenant.region + "-" + tempIds + " check_service_status is error")
            for sid in service_ids:
                child = {}
                child["status"] = "failure"
                result[sid] = child
        return JsonResponse(result)


class AllTenantsUsedResource(AuthedView):
    def init_request(self, *args, **kwargs):
        self.cookie_region = self.request.COOKIES.get('region')
        self.tenant_region = TenantRegionInfo.objects.get(tenant_id=self.tenant.tenant_id,
                                                          region_name=self.cookie_region)
    
    @method_perf_time
    @perm_required('tenant.tenant_access')
    def get(self, request, *args, **kwargs):
        result = {}
        try:
            service_ids = []
            serviceIds = ""
            service_list = TenantServiceInfo.objects.filter(tenant_id=self.tenant.tenant_id,
                                                            service_region=self.cookie_region).values(
                'ID', 'service_id', 'min_node', 'min_memory')
            if self.has_perm('tenant.list_all_services'):
                for s in service_list:
                    service_ids.append(s['service_id'])
                    if len(serviceIds) > 0:
                        serviceIds = serviceIds + ","
                    serviceIds = serviceIds + "'" + s["service_id"] + "'"
                    result[s['service_id'] + "_running_memory"] = s["min_node"] * s["min_memory"]
            else:
                service_pk_list = PermRelService.objects.filter(user_id=self.user.pk).values_list('service_id',
                                                                                                  flat=True)
                for s in service_list:
                    if s['ID'] in service_pk_list:
                        service_ids.append(s['service_id'])
                        if len(serviceIds) > 0:
                            serviceIds = serviceIds + ","
                        serviceIds = serviceIds + "'" + s["service_id"] + "'"
                        result[s['service_id'] + "_running_memory"] = s["min_node"] * s["min_memory"]
                        result[s['service_id'] + "_storage_memory"] = 0
            result["service_ids"] = service_ids
        except Exception as e:
            logger.exception(e)
        return JsonResponse(result)


class ServiceDetail(AuthedView):
    @method_perf_time
    @perm_required('view_service')
    def get(self, request, *args, **kwargs):
        result = {}
        try:
            if tenantAccountService.isOwnedMoney(self.tenant, self.service.service_region):
                result["totalMemory"] = 0
                result["status"] = "Owed"
                result["service_pay_status"] = "no_money"
                result["tips"] = "请为账户充值,然后重启应用"
            else:
                if self.service.deploy_version is None or self.service.deploy_version == "":
                    result["totalMemory"] = 0
                    result["status"] = "Undeployed"
                    result["service_pay_status"] = "debugging"
                    result["tips"] = "应用尚未运行"
                else:
                    body = regionClient.check_service_status(self.service.service_region, self.service.service_id)
                    status = body["status"]
                    service_pay_status, tips, cost_money, need_pay_money, start_time_str = self.get_pay_status(status)
                    result["service_pay_status"] = service_pay_status
                    result["tips"] = tips
                    result["cost_money"] = cost_money
                    result["need_pay_money"] = need_pay_money
                    result["start_time_str"] = start_time_str
                    if status == "running":
                        result["totalMemory"] = self.service.min_node * self.service.min_memory
                    else:
                        result["totalMemory"] = 0
                    result["status"] = status
        except Exception, e:
            logger.debug(self.service.service_region + "-" + self.service.service_id + " check_service_status is error")
            logger.exception(e)
            result["totalMemory"] = 0
            result['status'] = "failure"
            result["service_pay_status"] = "unknown"
            result["tips"] = "服务状态未知"
        return JsonResponse(result)
    
    def get_pay_status(self, service_current_status):
        
        rt_status = "unknown"
        rt_tips = "应用状态未知"
        rt_money = 0.0
        need_pay_money = 0.0
        start_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        status = service_current_status
        now = datetime.datetime.now()
        service_attach_info = ServiceAttachInfo.objects.get(tenant_id=self.tenant.tenant_id,
                                                            service_id=self.service.service_id)
        buy_start_time = service_attach_info.buy_start_time
        buy_end_time = service_attach_info.buy_end_time
        memory_pay_method = service_attach_info.memory_pay_method
        disk_pay_method = service_attach_info.disk_pay_method
        
        service_consume_list = ServiceConsume.objects.filter(tenant_id=self.tenant.tenant_id,
                                                             service_id=self.service.service_id).order_by("-ID")
        last_hour_cost = None
        if service_consume_list:
            last_hour_cost = service_consume_list[0]
            rt_money = last_hour_cost.pay_money
        
        service_unpay_bill_list = ServiceFeeBill.objects.filter(service_id=self.service.service_id,
                                                                tenant_id=self.tenant.tenant_id, pay_status="unpayed")
        buy_start_time_str = buy_start_time.strftime("%Y-%m-%d %H:%M:%S")
        diff_minutes = int((buy_start_time - now).total_seconds() / 60)
        if status == "running":
            if diff_minutes > 0:
                if memory_pay_method == "prepaid" or disk_pay_method == "prepaid":
                    if service_unpay_bill_list:
                        rt_status = "wait_for_pay"
                        rt_tips = "请于{0}前支付{1}元".format(buy_start_time_str, service_unpay_bill_list[0].prepaid_money)
                        need_pay_money = service_unpay_bill_list[0].prepaid_money
                        start_time_str = buy_start_time_str
                    else:
                        rt_status = "soon"
                        rt_tips = "将于{0}开始计费".format(buy_start_time_str)
                else:
                    rt_status = "soon"
                    rt_tips = "将于{0}开始计费".format(buy_start_time_str)
            else:
                if memory_pay_method == "prepaid" or disk_pay_method == "prepaid":
                    if now < buy_end_time:
                        rt_status = "show_money"
                        rt_tips = "包月包年项目于{0}到期".format(buy_end_time.strftime("%Y-%m-%d %H:%M:%S"))
                    else:
                        rt_status = "show_money"
                        rt_tips = "包月包年项目已于{0}到期,应用所有项目均按需结算".format(buy_end_time.strftime("%Y-%m-%d %H:%M:%S"))
                else:
                    rt_status = "show_money"
                    rt_tips = "当前应用所有项目均按小时结算"
        else:
            if diff_minutes > 0:
                rt_status = "debugging"
                rt_tips = "应用尚未运行"
            else:
                rt_status = "show_money"
                rt_tips = "应用尚未运行"
        
        return rt_status, rt_tips, rt_money, need_pay_money, start_time_str


class ServiceNetAndDisk(AuthedView):
    @method_perf_time
    @perm_required('view_service')
    def get(self, request, *args, **kwargs):
        result = {}
        try:
            tenant_id = self.tenant.tenant_id
            service_id = self.service.service_id
            result["memory"] = self.service.min_node * self.service.min_memory
            result["disk"] = 0
            result["bytesin"] = 0
            result["bytesout"] = 0
            result["disk_memory"] = 0
        except Exception, e:
            logger.exception(e)
        return JsonResponse(result)


class ServiceLog(AuthedView):
    @method_perf_time
    @perm_required('view_service')
    def get(self, request, *args, **kwargs):
        try:
            if self.service.deploy_version is None or self.service.deploy_version == "":
                return JsonResponse({})
            else:
                action = request.GET.get("action", "")
                service_id = self.service.service_id
                tenant_id = self.service.tenant_id
                if action == "operate":
                    # body = regionClient.get_userlog(self.service.service_region, service_id)
                    # eventDataList = body.get("event_data")
                    events = ServiceEvent.objects.filter(service_id=service_id).order_by("-start_time")
                    reEvents = []
                    for event in list(events):
                        eventRe = {}
                        eventRe["start_time"] = event.start_time
                        eventRe["end_time"] = event.end_time
                        eventRe["user_name"] = event.user_name
                        eventRe["message"] = event.message
                        eventRe["type"] = event.type
                        eventRe["status"] = event.status
                        reEvents.append(eventRe)
                    result = {}
                    result["log"] = reEvents
                    result["num"] = len(reEvents)
                    return JsonResponse(result)
                elif action == "service":
                    body = {}
                    body["tenant_id"] = tenant_id
                    body = regionClient.get_log(self.service.service_region, service_id, json.dumps(body))
                    return JsonResponse(body)
                elif action == "compile":
                    event_id = request.GET.get("event_id", "")
                    body = {}
                    if event_id != "":
                        body["tenant_id"] = tenant_id
                        body["event_id"] = event_id
                        body = regionClient.get_compile_log(self.service.service_region, service_id, json.dumps(body))
                    return JsonResponse(body)
        except Exception as e:
            logger.info("%s" % e)
        return JsonResponse({})


class ServiceCheck(AuthedView):
    @method_perf_time
    @perm_required('manage_service')
    def get(self, request, *args, **kwargs):
        result = {}
        try:
            requestNumber = request.GET.get("requestNumber", "0")
            reqNum = int(requestNumber)
            if reqNum > 0 and reqNum % 30 == 0:
                codeRepositoriesService.codeCheck(self.service)
            if self.service.language is None or self.service.language == "":
                tse = TenantServiceEnv.objects.get(service_id=self.service.service_id)
                dps = json.loads(tse.check_dependency)
                if dps["language"] == "false":
                    result["status"] = "check_error"
                else:
                    result["status"] = "checking"
            else:
                result["status"] = "checked"
                result["language"] = self.service.language
        except Exception as e:
            result["status"] = "checking"
            logger.debug(self.service.service_id + " not upload code")
        return JsonResponse(result)


class ServiceMappingPort(AuthedView):
    @perm_required('view_service')
    def get(self, request, *args, **kwargs):
        result = {}
        try:
            body = regionClient.findMappingPort(self.service.service_region, self.service.service_id)
            port = body["port"]
            ip = body["ip"]
            result["port"] = port
            result["ip"] = ip
        except Exception as e:
            logger.exception(e)
            result["port"] = 0
        return JsonResponse(result)


class ServiceDomainManager(AuthedView):
    @perm_required('manage_service')
    def post(self, request, *args, **kwargs):
        result = {}
        try:
            tenantService = self.service
            domain_name = request.POST["domain_name"]
            action = request.POST["action"]
            zhPattern = re.compile(u'[\u4e00-\u9fa5]+')
            match = zhPattern.search(domain_name.decode('utf-8'))
            container_port = request.POST.get("multi_port_bind", '0')
            if match:
                result["status"] = "failure"
                return JsonResponse(result)
            
            if action == "start":
                domainNum = ServiceDomain.objects.filter(domain_name=domain_name).count()
                if domainNum > 0:
                    result["status"] = "exist"
                    return JsonResponse(result)
                
                # num = ServiceDomain.objects.filter(service_id=self.service.service_id, container_port=container_port).count()
                old_domain_name = "goodrain"
                domain = {}
                domain["service_id"] = self.service.service_id
                domain["service_name"] = tenantService.service_alias
                domain["domain_name"] = domain_name
                domain["create_time"] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                domain["container_port"] = int(container_port)
                domaininfo = ServiceDomain(**domain)
                domaininfo.save()
                # if num == 0:
                #     domain = {}
                #     domain["service_id"] = self.service.service_id
                #     domain["service_name"] = tenantService.service_alias
                #     domain["domain_name"] = domain_name
                #     domain["create_time"] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                #     domain["container_port"] = int(container_port)
                #     domaininfo = ServiceDomain(**domain)
                #     domaininfo.save()
                # else:
                #     domain = ServiceDomain.objects.get(service_id=self.service.service_id, container_port=container_port)
                #     old_domain_name = domain.domain_name
                #     domain.domain_name = domain_name
                #     domain.container_port = int(container_port)
                #     domain.save()
                data = {}
                data["service_id"] = self.service.service_id
                data["new_domain"] = domain_name
                data["old_domain"] = old_domain_name
                data["pool_name"] = self.tenantName + "@" + self.serviceAlias + ".Pool"
                data["container_port"] = int(container_port)
                regionClient.addUserDomain(self.service.service_region, json.dumps(data))
                monitorhook.serviceMonitor(self.user.nick_name, self.service, 'domain_add', True)
            elif action == "close":
                servicerDomain = ServiceDomain.objects.get(service_id=self.service.service_id,
                                                           container_port=container_port, domain_name=domain_name)
                data = {}
                data["service_id"] = servicerDomain.service_id
                data["domain"] = servicerDomain.domain_name
                data["pool_name"] = self.tenantName + "@" + self.serviceAlias + ".Pool"
                data["container_port"] = int(container_port)
                regionClient.deleteUserDomain(self.service.service_region, json.dumps(data))
                ServiceDomain.objects.filter(service_id=self.service.service_id, container_port=container_port,
                                             domain_name=domain_name).delete()
                monitorhook.serviceMonitor(self.user.nick_name, self.service, 'domain_delete', True)
            result["status"] = "success"
        except Exception as e:
            logger.exception(e)
            result["status"] = "failure"
            monitorhook.serviceMonitor(self.user.nick_name, self.service, 'domain_manage', False)
        return JsonResponse(result)


class ServiceEnvVarManager(AuthedView):
    @perm_required('manage_service')
    def post(self, request, *args, **kwargs):
        result = {}
        try:
            id = request.POST["id"]
            nochange_name = request.POST["nochange_name"]
            name = request.POST["name"]
            attr_name = request.POST["attr_name"]
            attr_value = request.POST["attr_value"]
            attr_id = request.POST["attr_id"]
            name_arr = name.split(",")
            attr_name_arr = attr_name.split(",")
            attr_value_arr = attr_value.split(",")
            attr_id_arr = attr_id.split(",")
            logger.debug(attr_id)
            
            isNeedToRsync = True
            total_ids = []
            if id != "" and nochange_name != "":
                id_arr = id.split(',')
                nochange_name_arr = nochange_name.split(',')
                if len(id_arr) == len(nochange_name_arr):
                    for index, curid in enumerate(id_arr):
                        total_ids.append(curid)
                        stsev = TenantServiceEnvVar.objects.get(ID=curid)
                        stsev.attr_name = nochange_name_arr[index]
                        stsev.save()
            if name != "" and attr_name != "" and attr_value != "":
                if len(name_arr) == len(attr_name_arr) and len(attr_value_arr) == len(attr_name_arr):
                    # first delete old item
                    for item in attr_id_arr:
                        total_ids.append(item)
                    if len(total_ids) > 0:
                        TenantServiceEnvVar.objects.filter(service_id=self.service.service_id).exclude(
                            ID__in=total_ids).delete()
                    
                    # update and save env
                    for index, cname in enumerate(name_arr):
                        tmpId = attr_id_arr[index]
                        attr_name = attr_name_arr[index]
                        attr_value = attr_value_arr[index]
                        if int(tmpId) > 0:
                            tsev = TenantServiceEnvVar.objects.get(ID=int(tmpId))
                            tsev.attr_name = attr_name.lstrip().rstrip()
                            tsev.attr_value = attr_value.lstrip().rstrip()
                            tsev.save()
                        else:
                            tenantServiceEnvVar = {}
                            tenantServiceEnvVar["tenant_id"] = self.service.tenant_id
                            tenantServiceEnvVar["service_id"] = self.service.service_id
                            tenantServiceEnvVar["name"] = cname
                            tenantServiceEnvVar["attr_name"] = attr_name.lstrip().rstrip()
                            tenantServiceEnvVar["attr_value"] = attr_value.lstrip().rstrip()
                            tenantServiceEnvVar["is_change"] = True
                            TenantServiceEnvVar(**tenantServiceEnvVar).save()
            else:
                if len(total_ids) > 0:
                    TenantServiceEnvVar.objects.filter(service_id=self.service.service_id).exclude(
                        ID__in=total_ids).delete()
            
            # sync data to region
            if isNeedToRsync:
                baseService.create_service_env(self.service.tenant_id, self.service.service_id,
                                               self.service.service_region)
            result["status"] = "success"
        except Exception as e:
            logger.exception(e)
            result["status"] = "failure"
        return JsonResponse(result)


class ServiceBranch(AuthedView):
    def get_gitlab_branchs(self, parsed_git_url):
        project_id = self.service.git_project_id
        if project_id > 0:
            branchlist = codeRepositoriesService.getProjectBranches(project_id)
            branchs = [e['name'] for e in branchlist]
            return branchs
        else:
            return [self.service.code_version]
    
    def get_github_branchs(self, parsed_git_url):
        user = Users.objects.only('github_token').get(pk=self.service.creater)
        token = user.github_token
        owner = parsed_git_url.owner
        repo = parsed_git_url.repo
        branchs = []
        try:
            repos = codeRepositoriesService.gitHub_ReposRefs(owner, repo, token)
            reposList = json.loads(repos)
            for reposJson in reposList:
                ref = reposJson["ref"]
                branchs.append(ref.split("/")[2])
        except Exception, e:
            logger.error('client_error', e)
        return branchs
    
    @perm_required('view_service')
    def get(self, request, *args, **kwargs):
        parsed_git_url = git_url_parse(self.service.git_url)
        host = parsed_git_url.host
        if host is not None:
            if parsed_git_url.host == 'code.goodrain.com':
                branchs = self.get_gitlab_branchs(parsed_git_url)
            elif parsed_git_url.host.endswith('github.com'):
                branchs = self.get_github_branchs(parsed_git_url)
            else:
                branchs = [self.service.code_version]
            result = {"current": self.service.code_version, "branchs": branchs}
            return JsonResponse(result, status=200)
        else:
            return JsonResponse({}, status=200)
    
    @perm_required('deploy_service')
    def post(self, request, *args, **kwargs):
        branch = request.POST.get('branch')
        self.service.code_version = branch
        self.service.save(update_fields=['code_version'])
        return JsonResponse({"ok": True}, status=200)


class ServicePort(AuthedView):
    def check_port_alias(self, port_alias):
        if not re.match(r'^[A-Z][A-Z0-9_]*$', port_alias):
            return False, u"格式不符合要求^[A-Z][A-Z0-9_]"
        
        if TenantServicesPort.objects.filter(service_id=self.service.service_id, port_alias=port_alias).exists():
            return False, u"别名冲突"
        
        return True, port_alias
    
    def check_port(self, port):
        if not re.match(r'^\d{2,5}$', str(port)):
            return False, u"格式不符合要求^\d{2,5}"
        
        if self.service.code_from == "image_manual":
            if port > 65535 or port < 1:
                return False, u"端口号必须在1~65535之间！"
        else:
            if port > 65535 or port < 1025:
                return False, u"端口号必须在1025~65535之间！"
        
        if TenantServicesPort.objects.filter(service_id=self.service.service_id, container_port=port).exists():
            return False, u"端口冲突"
        
        return True, port
    
    @perm_required("manage_service")
    def post(self, request, port, *args, **kwargs):
        action = request.POST.get("action")
        deal_port = TenantServicesPort.objects.get(service_id=self.service.service_id, container_port=int(port))
        
        data = {"port": int(port)}
        if action == 'change_protocol':
            protocol = request.POST.get("value")
            deal_port.protocol = protocol
            # 判断stream协议的对外数量
            if protocol == "stream":
                outer_num = TenantServicesPort.objects.filter(service_id=self.service.service_id,
                                                              protocol="stream").count()
                if outer_num == 1:
                    return JsonResponse({"success": False, "code": 410, "info": u"对外stream端口只支持一个"})
            data.update({"modified_field": "protocol", "current_value": protocol})
        elif action == 'open_outer':
            deal_port.is_outer_service = True
            data.update({"modified_field": "is_outer_service", "current_value": True})
            if deal_port.mapping_port == 0:
                deal_port.mapping_port = 1
                data.update({"mapping_port": 1})
        elif action == 'close_outer':
            deal_port.is_outer_service = False
            data.update({"modified_field": "is_outer_service", "current_value": False})
        elif action == 'close_inner':
            deal_port.is_inner_service = False
            data.update({"modified_field": "is_inner_service", "current_value": False})
        elif action == 'open_inner':
            if bool(deal_port.port_alias) is False:
                return JsonResponse({"success": False, "info": u"请先为端口设置别名", "code": 409})
            deal_port.is_inner_service = True
            data.update({"modified_field": "is_inner_service", "current_value": True})
            logger.info(deal_port.mapping_port)
            baseService = BaseTenantService()
            if deal_port.mapping_port <= 1:
                mapping_port = baseService.prepare_mapping_port(self.service, deal_port.container_port)
                deal_port.mapping_port = mapping_port
                deal_port.save(update_fields=['mapping_port'])
                TenantServiceEnvVar.objects.filter(service_id=deal_port.service_id,
                                                   container_port=deal_port.container_port).delete()
                baseService.saveServiceEnvVar(self.service.tenant_id, self.service.service_id, deal_port.container_port,
                                              u"连接地址",
                                              deal_port.port_alias + "_HOST", "127.0.0.1", False, scope="outer")
                baseService.saveServiceEnvVar(self.service.tenant_id, self.service.service_id, deal_port.container_port,
                                              u"端口",
                                              deal_port.port_alias + "_PORT", mapping_port, False, scope="outer")
                data.update({"mapping_port": mapping_port})
            else:
                # 兼容旧的非对内服务, mapping_port有正常值
                unique = TenantServicesPort.objects.filter(tenant_id=deal_port.tenant_id,
                                                           mapping_port=deal_port.mapping_port).count()
                logger.debug("debug", "unique count is {}".format(unique))
                if unique > 1:
                    new_mapping_port = baseService.prepare_mapping_port(self.service, deal_port.container_port)
                    logger.debug("debug", "new_mapping_port is {}".format(new_mapping_port))
                    deal_port.mapping_port = new_mapping_port
                    deal_port.save(update_fields=['mapping_port'])
                    data.update({"mapping_port": new_mapping_port})
            
            port_envs = TenantServiceEnvVar.objects.filter(service_id=deal_port.service_id,
                                                           container_port=deal_port.container_port).values(
                'container_port', 'name', 'attr_name', 'attr_value', 'is_change', 'scope')
            data.update({"port_envs": list(port_envs)})
        elif action == 'change_port_alias':
            new_port_alias = request.POST.get("value")
            success, reason = self.check_port_alias(new_port_alias)
            # todo 同一租户下别名不能重复
            tenant_alias_num = TenantServicesPort.objects.filter(tenant_id=self.service.tenant_id,
                                                                 port_alias=new_port_alias).count()
            if tenant_alias_num > 0:
                return JsonResponse({"success": False, "info": "同一租户下别名不能重复", "code": 400}, status=400)
            if not success:
                return JsonResponse({"success": False, "info": reason, "code": 400}, status=400)
            else:
                old_port_alias = deal_port.port_alias
                deal_port.port_alias = new_port_alias
                envs = TenantServiceEnvVar.objects.only('attr_name').filter(service_id=deal_port.service_id,
                                                                            container_port=deal_port.container_port)
                for env in envs:
                    new_attr_name = new_port_alias + env.attr_name.replace(old_port_alias, '')
                    env.attr_name = new_attr_name
                    env.save()
                port_envs = TenantServiceEnvVar.objects.filter(service_id=deal_port.service_id,
                                                               container_port=deal_port.container_port).values(
                    'container_port', 'name', 'attr_name', 'attr_value', 'is_change', 'scope')
                # 处理mysql别名
                if self.service.service_type == 'mysql':
                    try:
                        mysql_envs = TenantServiceEnvVar.objects.only('attr_name') \
                            .filter(service_id=deal_port.service_id,
                                    attr_name__in=['MYSQL_USER', 'MYSQL_PASS', '{0}_USER'.format(old_port_alias),
                                                   '{0}_PASS'.format(old_port_alias)])
                        for env in mysql_envs:
                            old_attr_name = env.attr_name.replace(old_port_alias, '')
                            if old_attr_name == env.attr_name:
                                old_attr_name = env.attr_name.replace('MYSQL', '')
                            env.attr_name = new_port_alias + old_attr_name
                            env.save()
                    except Exception as e:
                        logger.error(e)
                    data.update({'old_port_alias': old_port_alias})
                data.update(
                    {"modified_field": "port_alias", "current_value": new_port_alias, "port_envs": list(port_envs)})
        elif action == 'change_port':
            new_port = int(request.POST.get("value"))
            success, reason = self.check_port(new_port)
            if not success:
                return JsonResponse({"success": False, "info": reason, "code": 400}, status=400)
            else:
                if TenantServicesPort.objects.filter(service_id=self.service.service_id,
                                                     container_port=deal_port.container_port,
                                                     is_outer_service=True).count() > 0:
                    return JsonResponse({"success": False, "code": 400, "info": u"请关闭外部访问"}, status=400)
                
                if TenantServicesPort.objects.filter(service_id=self.service.service_id,
                                                     container_port=deal_port.container_port,
                                                     is_inner_service=True).count() > 0:
                    return JsonResponse({"success": False, "code": 400, "info": u"请关闭对外服务"}, status=400)
                
                old_port = deal_port.container_port
                deal_port.container_port = new_port
                TenantServiceEnvVar.objects.filter(service_id=deal_port.service_id, container_port=old_port).update(
                    container_port=new_port)
                data.update({"modified_field": "port", "current_value": new_port})
        try:
            regionClient.manageServicePort(self.service.service_region, self.service.service_id, json.dumps(data))
            monitorhook.serviceMonitor(self.user.nick_name, self.service, 'app_outer', True)
            deal_port.save()
            
            if action == 'close_outer' or action == 'open_outer':
                # 兼容旧的服务单端口
                if self.service.port_type == "one_outer":
                    # 检查服务已经存在对外端口
                    outer_port_num = TenantServicesPort.objects.filter(service_id=self.service.service_id,
                                                                       is_outer_service=True).count()
                    if outer_port_num > 1:
                        cur_port_type = "multi_outer"
                        self.service.port_type = cur_port_type
                        self.service.save()
                        
                        data1 = {"port": int(port)}
                        data1.update({"modified_field": "mult_port", "current_value": True, "port_type": cur_port_type})
                        regionClient.manageServicePort(self.service.service_region, self.service.service_id,
                                                       json.dumps(data1))
            return JsonResponse({"success": True, "info": u"更改成功"}, status=200)
        except Exception as e:
            logger.exception(e)
            monitorhook.serviceMonitor(self.user.nick_name, self.service, 'app_outer', False)
            return JsonResponse({"success": False, "info": u"更改失败", "code": 500}, status=200)
    
    def get(self, request, port, *args, **kwargs):
        deal_port = TenantServicesPort.objects.get(service_id=self.service.service_id, container_port=int(port))
        data = {"environment": []}
        
        if deal_port.is_inner_service:
            for port_env in TenantServiceEnvVar.objects.filter(service_id=self.service.service_id,
                                                               container_port=deal_port.container_port):
                data["environment"].append({
                    "desc": port_env.name, "name": port_env.attr_name, "value": port_env.attr_value
                })
        if deal_port.is_outer_service:
            service_region = self.service.service_region
            if deal_port.protocol == 'stream':
                body = regionClient.findMappingPort(self.service.service_region, self.service.service_id)
                cur_region = service_region.replace("-1", "")
                domain = "{0}.{1}.{2}-s1.goodrain.net".format(self.service.service_alias, self.tenant.tenant_name,
                                                              cur_region)
                if settings.STREAM_DOMAIN_URL[service_region] != "":
                    domain = settings.STREAM_DOMAIN_URL[service_region]
                
                data["outer_service"] = {
                    "domain": domain,
                    "port": body["port"],
                }
            elif deal_port.protocol == 'http':
                data["outer_service"] = {
                    "domain": "{0}.{1}{2}".format(self.service.service_alias, self.tenant.tenant_name,
                                                  settings.WILD_DOMAINS[service_region]),
                    "port": settings.WILD_PORTS[self.service.service_region]
                }
        
        return JsonResponse(data, status=200)


class ServiceEnv(AuthedView):
    @perm_required("manage_service")
    def post(self, request, *args, **kwargs):
        action = request.POST.get('action')
        
        if action == 'add_attr':
            name = request.POST.get('name', '')
            attr_name = request.POST.get('attr_name')
            attr_value = request.POST.get('attr_value')
            scope = request.POST.get('scope', 'inner')
            attr_name = attr_name.lstrip().rstrip()
            attr_value = attr_value.lstrip().rstrip()
            
            form = EnvCheckForm(request.POST)
            if not form.is_valid():
                return JsonResponse({"success": False, "code": 400, "info": u"变量名不合法"})
            
            if TenantServiceEnvVar.objects.filter(service_id=self.service.service_id, attr_name=attr_name).exists():
                return JsonResponse({"success": False, "code": 409, "info": u"变量名冲突"})
            else:
                attr = {
                    "tenant_id": self.service.tenant_id, "service_id": self.service.service_id, "name": name,
                    "attr_name": attr_name, "attr_value": attr_value, "is_change": True, "scope": scope
                }
                env = TenantServiceEnvVar.objects.create(**attr)
                data = {"action": "add", "attrs": attr}
                regionClient.createServiceEnv(self.service.service_region, self.service.service_id, json.dumps(data))
                return JsonResponse(
                    {"success": True, "info": u"创建成功", "pk": env.pk, "attr_name": attr_name, "attr_value": attr_value,
                     "name": name})
        elif action == 'del_attr':
            attr_name = request.POST.get("attr_name")
            TenantServiceEnvVar.objects.filter(service_id=self.service.service_id, attr_name=attr_name).delete()
            
            data = {"action": "delete", "attr_names": [attr_name]}
            regionClient.createServiceEnv(self.service.service_region, self.service.service_id, json.dumps(data))
            return JsonResponse({"success": True, "info": u"删除成功"})


class ServiceMnt(AuthedView):
    @perm_required('manage_service')
    def post(self, request, *args, **kwargs):
        result = {}
        action = request.POST["action"]
        dep_service_alias = request.POST["dep_service_alias"]
        try:
            tenant_id = self.tenant.tenant_id
            service_id = self.service.service_id
            if action == "add":
                baseService.create_service_mnt(tenant_id, service_id, dep_service_alias, self.service.service_region)
            elif action == "cancel":
                baseService.cancel_service_mnt(tenant_id, service_id, dep_service_alias, self.service.service_region)
            result["status"] = "success"
        except Exception, e:
            logger.exception(e)
            result["status"] = "failure"
        return JsonResponse(result)


class ServiceNewPort(AuthedView):
    @perm_required("manage_service")
    def post(self, request, *args, **kwargs):
        action = request.POST.get('action')
        
        if action == 'add_port':
            port_port = request.POST.get('port_port', "5000")
            port_protocol = request.POST.get('port_protocol', "http")
            port_alias = request.POST.get('port_alias', "")
            port_inner = request.POST.get('port_inner', "0")
            port_outter = request.POST.get('port_outter', "0")
            
            if not re.match(r'^[0-9]*$', port_port):
                return JsonResponse({"success": False, "code": 400, "info": u"端口不合法"})
            
            port_port = int(port_port)
            port_inner = int(port_inner)
            port_outter = int(port_outter)
            
            if port_port <= 0:
                return JsonResponse({"success": False, "code": 400, "info": u"端口需大于零"})
            if port_inner != 0:
                if not re.match(r'^[A-Z][A-Z0-9_]*$', port_alias):
                    return JsonResponse({"success": False, "code": 400, "info": u"别名不合法"})
            # todo 判断端口别名是否重复
            tenant_alias_num = TenantServicesPort.objects.filter(tenant_id=self.service.tenant_id,
                                                                 port_alias=port_alias).count()
            if tenant_alias_num > 0:
                return JsonResponse({"success": False, "code": 400, "info": u"同一租户下别名不能重复"})
            
            if TenantServicesPort.objects.filter(service_id=self.service.service_id, container_port=port_port).exists():
                return JsonResponse({"success": False, "code": 409, "info": u"容器端口冲突"})
            # 对外stream只能开一个
            if port_protocol == "stream":
                outer_num = TenantServicesPort.objects.filter(service_id=self.service.service_id,
                                                              protocol="stream").count()
                if outer_num == 1:
                    return JsonResponse({"success": False, "code": 410, "info": u"对外stream端口只支持一个"})
            mapping_port = 0
            if port_inner == 1 and port_protocol == "stream":
                mapping_port = baseService.prepare_mapping_port(self.service, port_port)
            port = {
                "tenant_id": self.service.tenant_id, "service_id": self.service.service_id,
                "container_port": port_port, "mapping_port": mapping_port, "protocol": port_protocol,
                "port_alias": port_alias,
                "is_inner_service": port_inner, "is_outer_service": port_outter
            }
            TenantServicesPort.objects.create(**port)
            data = {"action": "add", "ports": port}
            regionClient.createServicePort(self.service.service_region, self.service.service_id, json.dumps(data))
            return JsonResponse({"success": True, "info": u"创建成功"})
        elif action == 'del_port':
            if TenantServicesPort.objects.filter(service_id=self.service.service_id).count() == 1:
                return JsonResponse({"success": False, "code": 409, "info": u"服务至少保留一个端口"})
            
            port_port = request.POST.get("port_port")
            num = ServiceDomain.objects.filter(service_id=self.service.service_id, container_port=port_port).count()
            if num > 0:
                return JsonResponse({"success": False, "code": 409, "info": u"请先解绑该端口绑定的域名"})
            
            if TenantServicesPort.objects.filter(service_id=self.service.service_id, container_port=port_port,
                                                 is_outer_service=True).count() > 0:
                return JsonResponse({"success": False, "code": 409, "info": u"请关闭外部访问"})
            
            if TenantServicesPort.objects.filter(service_id=self.service.service_id, container_port=port_port,
                                                 is_inner_service=True).count() > 0:
                return JsonResponse({"success": False, "code": 409, "info": u"请关闭对外服务"})
            
            TenantServicesPort.objects.filter(service_id=self.service.service_id, container_port=port_port).delete()
            TenantServiceEnvVar.objects.filter(service_id=self.service.service_id, container_port=port_port).delete()
            ServiceDomain.objects.filter(service_id=self.service.service_id, container_port=port_port).delete()
            data = {"action": "delete", "port_ports": [port_port]}
            regionClient.createServicePort(self.service.service_region, self.service.service_id, json.dumps(data))
            return JsonResponse({"success": True, "info": u"删除成功"})


class ServiceDockerContainer(AuthedView):
    @perm_required('manage_service')
    def get(self, request, *args, **kwargs):
        data = {}
        try:
            data = regionClient.serviceContainerIds(self.service.service_region, self.service.service_id)
            logger.info(data)
        except Exception, e:
            logger.exception(e)
        return JsonResponse(data)
    
    @perm_required('manage_service')
    def post(self, request, *args, **kwargs):
        response = JsonResponse({"success": True})
        try:
            c_id = request.POST.get("c_id", "")
            h_id = request.POST.get("h_id", "")
            logger.info("c_id=" + c_id)
            logger.info("h_id=" + h_id)
            if c_id != "" and h_id != "":
                if settings.DOCKER_WSS_URL.get("is_wide_domain", False):
                    fields = h_id.split('.')
                    new_fields = map(lambda x: int(x) + int(fields[len(x)]), fields)
                    key = '{:02X}{:02X}{:02X}{:02X}'.format(*new_fields)
                    response.set_cookie('docker_h_id', key)
                else:
                    response.set_cookie('docker_h_id', h_id)
                response.set_cookie('docker_c_id', c_id)
                response.set_cookie('docker_s_id', self.service.service_id)
            return response
        except Exception as e:
            logger.exception(e)
            response = JsonResponse({"success": False})
        return response


class ServiceVolumeView(AuthedView):
    """添加,删除持久化数据目录"""
    
    SYSDIRS = ["/", "/bin", "/boot", "/dev", "/etc", "/home",
               "/lib", "/lib64", "/opt", "/proc", "/root", "/sbin",
               "/srv", "/sys", "/tmp", "/usr", "/var",
               "/usr/local", "/usr/sbin", "/usr/bin",
               ]
    
    @perm_required('manage_service')
    def post(self, request, *args, **kwargs):
        result = {}
        action = request.POST["action"]
        try:
            if action == "add":
                volume_path = request.POST.get("volume_path")
                # category = self.service.category
                language = self.service.language
                if self.service.image != "goodrain.me/runner":
                    if not volume_path.startswith("/"):
                        result["status"] = "failure"
                        result["code"] = "303"
                        return JsonResponse(result)
                    if volume_path in self.SYSDIRS:
                        result["status"] = "failure"
                        result["code"] = "304"
                        return JsonResponse(result)
                else:
                    if volume_path.startswith("/"):
                        volume_path = "/app" + volume_path
                    else:
                        volume_path = "/app/" + volume_path
                # volume_path不能重复
                all_volume_path = TenantServiceVolume.objects.filter(service_id=self.service.service_id).values(
                    "volume_path")
                if len(all_volume_path):
                    for path in list(all_volume_path):
                        if path["volume_path"] == volume_path:
                            result["status"] = "failure"
                            result["code"] = "305"
                            return JsonResponse(result)
                        if path["volume_path"].startswith(volume_path + "/"):
                            result["status"] = "failure"
                            result["code"] = "307"
                            return JsonResponse(result)
                        if volume_path.startswith(path["volume_path"] + "/"):
                            result["status"] = "failure"
                            result["code"] = "306"
                            return JsonResponse(result)
                
                if self.service.host_path is None or self.service.host_path == "":
                    self.service.host_path = "/grdata/tenant/" + self.service.tenant_id + "/service/" + self.service.service_id
                    self.service.save()
                
                volume_id = baseService.create_service_volume(self.service, volume_path)
                if volume_id:
                    result["volume"] = {
                        "ID": volume_id,
                        "volume_path": volume_path,
                    }
                    result["status"] = "success"
                    result["code"] = "200"
                else:
                    result["status"] = "failure"
                    result["code"] = "500"
            elif action == "cancel":
                volume_id = request.POST.get("volume_id")
                flag = baseService.cancel_service_volume(self.service, volume_id)
                if flag:
                    result["status"] = "success"
                    result["code"] = "200"
                else:
                    result["status"] = "failure"
                    result["code"] = "500"
        except Exception as e:
            logger.exception(e)
            result["status"] = "failure"
            result["code"] = "500"
        return JsonResponse(result)


class MntShareTypeView(AuthedView):
    @perm_required('manage_service')
    def post(self, request, *args, **kwargs):
        volume_type = request.POST.get("volume_type", "")
        result = {}
        try:
            if volume_type != "":
                tenantServiceInfo = TenantServiceInfo.objects.get(service_id=self.service.service_id)
                if tenantServiceInfo.volume_type != volume_type:
                    tenantServiceInfo.volume_type = volume_type
                    tenantServiceInfo.save()
                    baseService.custom_mnt_shar_type(self.service, volume_type)
            result["status"] = "ok"
        except Exception as e:
            logger.exception(e)
            result["status"] = "failure"
        return JsonResponse(result)


class ContainerStatsView(AuthedView):
    @perm_required('manage_service')
    def get(self, request, *args, **kwargs):
        data = {}
        result = []
        try:
            data = regionClient.tenantServiceStats(self.service.service_region, self.service.service_id)
        except Exception as e:
            logger.exception(e)
        return JsonResponse(data)


class ServiceNameChangeView(AuthedView):
    @perm_required('manage_service')
    def post(self, request, *args, **kwargs):
        new_service_cname = request.POST.get("new_service_cname", "")
        service_alias = request.POST.get("service_alias")
        result = {}
        try:
            if new_service_cname.strip() != "":
                TenantServiceInfo.objects.filter(service_alias=service_alias, tenant_id=self.tenant.tenant_id).update(
                    service_cname=new_service_cname)
                result["ok"] = True
                result["info"] = "修改成功"
                result["new_service_cname"] = new_service_cname
        except Exception as e:
            logger.exception(e)
            result["ok"] = False
            result["info"] = "修改失败"
        return JsonResponse(result)


class ServiceLogTypeView(AuthedView):
    def get(self, request, *args, **kwargs):
        result = {}
        try:
            self.cookie_region = self.request.COOKIES.get('region')
            services = TenantServiceInfo.objects.filter(service_type__in=["elasticsearch", "mongodb", "influxdb"],
                                                        tenant_id=self.tenant.tenant_id,
                                                        service_region=self.cookie_region)
            i = 0
            for service in services:
                tmp = {}
                tmp["service_id"] = service.service_id
                tmp["service_cname"] = service.service_cname
                tmp["service_type"] = service.service_type
                tmp["service_alias"] = service.service_alias
                result[i] = tmp
                i += 1
        except Exception as e:
            logger.exception(e)
            result["ok"] = False
            result["info"] = "获取失败"
        return JsonResponse(result)

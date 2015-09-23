function goto_deploy(tenantName, service_alias) {
	window.location.href = "/apps/" + tenantName + "/" + service_alias
			+ "/detail/"
}

function service_oneKeyDeploy(categroy, serviceAlias, tenantName, isreload) {
	$("#onekey_deploy").attr('disabled', "true")
	_url = "/ajax/" + tenantName + '/' + serviceAlias + "/app-deploy/"
	if (categroy == "application") {
		_url = "/ajax/" + tenantName + '/' + serviceAlias + "/app-deploy/"
	} else {
		swal("暂时不支持")
		return;
	}
	$.ajax({
		type : "POST",
		url : _url,
		cache : false,
		beforeSend : function(xhr, settings) {
			var csrftoken = $.cookie('csrftoken');
			xhr.setRequestHeader("X-CSRFToken", csrftoken);
		},
		success : function(msg) {
			var dataObj = msg;
			if (dataObj["status"] == "success") {
				swal("操作成功")
			} else if (dataObj["status"] == "owed") {
				swal("余额不足请及时充值")
			} else if (dataObj["status"] == "language") {
				swal("应用语言监测未通过")
				forurl = "/apps/" + tenantName + "/" + serviceAlias
						+ "/detail/"
				window.open(forurl, target = "_parent")
			} else if (dataObj["status"] == "often") {
				swal("上次部署正在进行中，请稍后再试")
			} else if (dataObj["status"] == "over_memory") {
				swal("免费资源已达上限，不能升级")
			} else if (dataObj["status"] == "over_money") {
				swal("余额不足，不能升级")
			} else {
				swal("操作失败")
				$("#onekey_deploy").removeAttr("disabled")
			}
			if (isreload == 'yes') {
				forurl = "/apps/" + tenantName + "/" + serviceAlias
						+ "/detail/"
				window.open(forurl, target = "_parent")
			}
			$("#onekey_deploy").removeAttr("disabled")
		},
		error : function() {
			$("#onekey_deploy").removeAttr("disabled")
			// swal("系统异常");
		}
	})
}

function service_my_onOperation(service_id, service_alias, tenantName) {
	var taction = $("#operate_" + service_id).attr("data" + service_id)
	if (taction != "stop" && taction != "restart") {
		swal("系统异常");
		window.location.href = window.location.href;
	}
	$.ajax({
		type : "POST",
		url : "/ajax/" + tenantName + "/" + service_alias + "/manage",
		data : "service_id=" + service_id + "&action=" + taction,
		cache : false,
		beforeSend : function(xhr, settings) {
			var csrftoken = $.cookie('csrftoken');
			xhr.setRequestHeader("X-CSRFToken", csrftoken);
		},
		success : function(msg) {
			var dataObj = msg
			if (dataObj["status"] == "success") {
				swal("操作成功")
			} else if (dataObj["status"] == "often") {
				swal("上次操作正在进行中，稍后再试")
			} else if (dataObj["status"] == "owed") {
				swal("余额不足请及时充值")
			} else if (dataObj["status"] == "over_memory") {
				swal("免费资源已达上限，不能升级")
			} else if (dataObj["status"] == "over_money") {
				swal("余额不足，不能升级")
			} else {
				swal("操作失败")
			}
		},
		error : function() {
			swal("系统异常");
		}
	})
}

// 服务重启关闭
function service_onOperation(service_id, service_alias, tenantName) {
	var taction = $("#service_status_value").val()
	if (taction != "stop" && taction != "restart") {
		swal("参数异常");
		window.location.href = window.location.href;
	}
	$.ajax({
		type : "POST",
		url : "/ajax/" + tenantName + "/" + service_alias + "/manage",
		data : "service_id=" + service_id + "&action=" + taction,
		cache : false,
		beforeSend : function(xhr, settings) {
			var csrftoken = $.cookie('csrftoken');
			xhr.setRequestHeader("X-CSRFToken", csrftoken);
		},
		success : function(msg) {
			var dataObj = msg
			if (dataObj["status"] == "success") {
				swal("操作成功")
			} else if (dataObj["status"] == "often") {
				swal("上次操作正在进行中，稍后再试")
			} else if (dataObj["status"] == "owed") {
				swal("余额不足请及时充值")
			} else if (dataObj["status"] == "over_memory") {
				swal("免费资源已达上限，不能操作")
			} else if (dataObj["status"] == "over_money") {
				swal("余额不足，不能操作")
			} else {
				swal("操作失败")
			}
		},
		error : function() {
			swal("系统异常");
		}
	})
}

function domainSubmit(action, service_id, tenantName, service_alias) {
	if (action != "start" && action != "close") {
		swal("参数异常");
		window.location.href = window.location.href;
	}
	var domain_name = $("#service_app_name").val();
	if (domain_name == "") {
		swal("输入有效的域名");
		return;
	}
	$.ajax({
		type : "POST",
		url : "/ajax/" + tenantName + "/" + service_alias + "/domain",
		data : "service_id=" + service_id + "&domain_name=" + domain_name+"&action="+action,
		cache : false,
		beforeSend : function(xhr, settings) {
			var csrftoken = $.cookie('csrftoken');
			xhr.setRequestHeader("X-CSRFToken", csrftoken);
		},
		success : function(msg) {
			var dataObj = msg
			if (dataObj["status"] == "success") {
				swal("操作成功")
				$("#service_app_name").val("")
			} else if (dataObj["status"] == "limit"){
				swal("免费用户不允许")
			} else if (dataObj["status"] == "exist") {
				swal("域名已存在")
			} else {
				swal("操作失败")
			}
		},
		error : function() {
			swal("系统异常");
		}
	})
}

// 服务垂直升级
function service_upgrade(tenantName, service_alias) {
	var service_min_config = $("#serviceMemorys").val();
	memory = 128 * Math.pow(2, service_min_config - 1)
	cpu = 20 * Math.pow(2, service_min_config - 1)
	$.ajax({
		type : "post",
		url : "/ajax/" + tenantName + "/" + service_alias + "/upgrade",
		data : "action=vertical&memory=" + memory + "&cpu=" + cpu,
		cache : false,
		beforeSend : function(xhr, settings) {
			var csrftoken = $.cookie('csrftoken');
			xhr.setRequestHeader("X-CSRFToken", csrftoken);
		},
		success : function(msg) {
			var dataObj = msg;
			if (dataObj["status"] == "success") {
				swal("设置成功")
			} else if (dataObj["status"] == "owed") {
				swal("余额不足请及时充值")
			} else if (dataObj["status"] == "often") {
				swal("上次操作正在进行中，稍后再试")
			} else if (dataObj["status"] == "over_memory") {
				swal("免费资源已达上限，不能升级")
			} else if (dataObj["status"] == "over_money") {
				swal("余额不足，不能升级")
			} else {
				swal("设置失败")
			}
		},
		error : function() {
			swal("系统异常,请重试");
		}
	})
}

// 服务水平升级
function app_upgrade(tenantName, service_alias) {
	var service_min_node = $("#serviceNods").val();
	if (service_min_node >= 0) {
		$.ajax({
			type : "post",
			url : "/ajax/" + tenantName + "/" + service_alias + "/upgrade/",
			data : "action=horizontal&node_num=" + service_min_node,
			cache : false,
			beforeSend : function(xhr, settings) {
				var csrftoken = $.cookie('csrftoken');
				xhr.setRequestHeader("X-CSRFToken", csrftoken);
			},
			success : function(msg) {
				var dataObj = msg;
				if (dataObj["status"] == "success") {
					swal("设置成功")
				} else if (dataObj["status"] == "owed") {
					swal("余额不足请及时充值")
				} else if (dataObj["status"] == "often") {
					swal("上次操作正在进行中，稍后再试")
				} else if (dataObj["status"] == "over_memory") {
					swal("免费资源已达上限，不能升级")
				} else if (dataObj["status"] == "over_money") {
					swal("余额不足，不能升级")
				} else {
					swal("设置失败")
				}
			},
			error : function() {
				swal("系统异常,请重试");
			}
		})
	}
}

function delete_service(tenantName, service_alias) {
	swal({
		title : "确定删除当前服务吗？",
		type : "warning",
		showCancelButton : true,
		confirmButtonColor : "#DD6B55",
		confirmButtonText : "确定",
		cancelButtonText : "取消",
		closeOnConfirm : false,
		closeOnCancel : false
	}, function(isConfirm) {
		if (isConfirm) {
			$.ajax({
				type : "POST",
				url : "/ajax/" + tenantName + "/" + service_alias + "/manage/",
				data : "action=delete",
				cache : false,
				beforeSend : function(xhr, settings) {
					var csrftoken = $.cookie('csrftoken');
					xhr.setRequestHeader("X-CSRFToken", csrftoken);
					swal({
						title : "正在执行删除操作，请稍候...",
						text : "5秒后自动关闭",
						timer : 5000,
						showConfirmButton : false
					});
				},
				success : function(msg) {
					var dataObj = msg
					if (dataObj["status"] == "success") {
						swal("操作成功");
						window.location.href = "/apps/" + tenantName
					} else if (dataObj["status"] == "often") {
						swal("上次操作正在进行中，稍后再试")
					} else if (dataObj["status"] == "dependency") {
						swal("当前服务被依赖不能删除");
					} else {
						swal("操作失败");
					}
				},
				error : function() {
					swal("系统异常");
				}
			});
		} else {
			swal.close();
		}
	});
}

function service_protocol(opt_type, action, tenantName, service_alias) {
	if (action != "start" && action != "close" && action != "change") {
		swal("系统异常");
		window.location.href = window.location.href;
	}
	var protocol = ""
	var outer_service = "close"
	var inner_service = "close"
	var service_visitor_ip =""
	if (opt_type == "outer") {
		protocol = $("#protocol").val();
		outer_service = action
		service_visitor_ip = $("#service_visitor_ip").val()
	}
	if (opt_type == "inner") {
		inner_service = action
	}
	if(protocol == "stream" && action == "start"){
		if(service_visitor_ip == ""){
			swal("请填写访问ip");
			return false;
		}
		var re=/^(\d+)\.(\d+)\.(\d+)\.(\d+)$/g;
		if(!re.test(service_visitor_ip)){
			swal("请填写正确的访问ip");
			return false;
		}
	}
	$.ajax({
		type : "POST",
		url : "/ajax/" + tenantName + "/" + service_alias + "/manage/",
		data : "opt_type=" + opt_type + "&protocol=" + protocol
				+ "&action=protocol&inner_service=" + inner_service
				+ "&outer_service=" + outer_service+"&outer_ip="+service_visitor_ip,
		cache : false,
		beforeSend : function(xhr, settings) {
			var csrftoken = $.cookie('csrftoken');
			xhr.setRequestHeader("X-CSRFToken", csrftoken);
		},
		success : function(msg) {
			var dataObj = msg
			if (dataObj["status"] == "success") {
				swal("操作成功")
				if (action == "change"){
					if (window.location.href.indexOf("fr=") < 0){
						window.location.href = window.location.href + "?fr=settings";
					}else{
						window.location.href = window.location.href
					}
				}
			} else if (dataObj["status"] == "often") {
				swal("上次操作正在进行中，稍后再试")
			} else if (dataObj["status"] == "owed") {
				swal("余额不足请及时充值")
			} else if (dataObj["status"] == "over_memory") {
				swal("免费资源已达上限，不能升级")
			} else if (dataObj["status"] == "over_money") {
				swal("余额不足，不能升级")
			} else {
				swal("操作失败")
			}
		},
		error : function() {
			swal("系统异常");
		}
	})
}


function buid_relation(action,curServiceName,depServiceName,tenantName){
	if (action != "add" && action != "cancel") {
		swal("系统异常");
		window.location.href = window.location.href;
	}
	$.ajax({
		type : "POST",
		url : "/ajax/" + tenantName + "/" + curServiceName + "/relation",
		data : "dep_service_alias=" + depServiceName + "&action="+action,
		cache : false,
		beforeSend : function(xhr, settings) {
			var csrftoken = $.cookie('csrftoken');
			xhr.setRequestHeader("X-CSRFToken", csrftoken);
		},
		success : function(msg) {
			var dataObj = msg
			if (dataObj["status"] == "success") {
				swal("操作成功")
				if (window.location.href.indexOf("fr=") < 0){
					window.location.href = window.location.href + "?fr=relations";
				}else{
					window.location.href = window.location.href
				}				
			} else {
				swal("操作失败")
			}
		},
		error : function() {
			// swal("系统异常");
		}
	})
}
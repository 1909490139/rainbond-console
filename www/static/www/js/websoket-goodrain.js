var websocket_uri = "ws://123.59.40.70:6060/websocket"

WEB_SOCKET_SWF_LOCATION = '/static/www/js/WebSocketMain.swf';
WEB_SOCKET_DEBUG = true;
var browser_ua = navigator.userAgent.toLowerCase();
if (browser_ua.indexOf('360se') != -1 || browser_ua.indexOf('maxthon') != -1) {
	WEB_SOCKET_SWF_LOCATION += '?v=' + new Date().getTime().toString();
}

function extPushWebSocketClient() {

}

function extPushWebSocketConnect(service_id,tenantName, serviceAlias) {
	var that = this;
	var websocket_uri = '';
	this.requestUrl = '';
	$.ajax({
		type : "GET",
		url : "/ajax/" + tenantName + "/" + serviceAlias + "/log_instance",
		data : {},
		cache : false,
		beforeSend : function(xhr, settings) {
			var csrftoken = $.cookie('csrftoken');
			xhr.setRequestHeader("X-CSRFToken", csrftoken);
		},
		success : function(msg) {
			websocket_uri = msg["ws_url"];
			that.requestUrl = websocket_uri; // 扩充服务器
			that.socketStore = new WebSocket(websocket_uri);
			if( msg["ok"] )
			{

			}
			else{
				var str = '<p>'+msg["info"]+'</p>';
				$(str).prependTo($("#docker_log"));
			}
		},
		error : function() {
			swal("系统异常");
		}
	});
	//this.requestUrl = websocket_uri.split(","); // 扩充服务器
	this.socketStore = ''; // web_socket对象存储
	this.keeplivetime = 5; // 心跳时间
	this.trytimes = 1; // 重试次数
	this.linkIndex = 0 // parseInt(Math.random() * 1); //下标值，连接地址随机0, 1
}

extPushWebSocketConnect.prototype = {
	// 连接初始化
	init : function(obj,topic) {
		this.socketStore = '';
		var self = this, url = this.requestUrl;
		if( url )
		{
			this.socketStore = new WebSocket(url);
			console.log(url);
		}
		// alert(this.client)
		this.socketStore.onopen = function() {
			// if (!$.browser.msie) {
			// console.log("extPush:onopen");
			// }
			if (topic != undefined && topic != "undefined") {
				self.sendCmd(topic);
			}
			self.trytimes = 1;
		};
		this.socketStore.onmessage = function(e) {
			if (e.data) {
				client.onMessage(e.data)
			}
		};
		this.socketStore.onclose = function() {
			// if (!$.browser.msie) {
			// console.log("extPush:onclose");
			// }
			self.closeWebSocket();
			self.init(client)
		};
		this.socketStore.onerror = function() {
			// if (!$.browser.msie) {
			// console.log("extPush:onerror");
			// }
		};
		//this.keepWebSocketLive(client, topic, cmd, key, info);
		this.windowCloseCheck();
	},
	sendCmd : function(topic) {
		var self = this;
		self.socketStore.send("service_id="+topic);
	},
	closeWebSocket : function() {
		var self = this;
		self.socketStore.close();
	},
	keepWebSocketLive : function(client, topic, cmd, key, info) {
		var self = this;
		clearInterval(window.sockeyTryAgain);
		clearTimeout(window.socketJoinSucc);
		clearTimeout(window.resetCheckFlag);
		window.sockeyTryAgain = setInterval(function() {
			if (self.socketStore.readyState == 0
					|| self.socketStore.readyState == 2
					|| self.socketStore.readyState == 3
					|| self.socketStore.bufferedAmount > 0) {
				self.closeWebSocket();
				self.init(client, topic, cmd, key,info)
			} else {
				self.sendCmd("check", "1", "1")
				//self.init(client, topic, cmd, key,info)
			}
		}, 1000 * 12 * self.keeplivetime);
	},
	windowCloseCheck : function() {
		var self = this;
		// if ($.browser.msie) {
		// window.onbeforeunload = onbeforeunload_handler;
		// function onbeforeunload_handler() {
		// self.closeWebSocket();
		//			}
		//		}
	}
};

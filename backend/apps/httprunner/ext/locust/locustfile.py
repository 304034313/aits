import random
import logging
from prometheus_client import start_http_server, Counter, Histogram, Gauge

from locust import task, HttpUser, between, events
from httprunner.ext.locust import prepare_locust_tests

# ==========================================
# 1. Prometheus 探针 (数据发射器)
# ==========================================
locust_requests_total = Counter('locust_requests_total', 'Total requests', ['method', 'name', 'result'])
locust_request_latency_seconds = Histogram('locust_request_latency_seconds', 'Request latency in seconds', ['method', 'name'])
locust_users = Gauge('locust_users', 'Current number of users')

@events.init.add_listener
def on_locust_init(environment, **kwargs):
    """在 Locust 引擎启动时，自动开启 8089 端口暴露指标"""
    try:
        # 强制绑定 0.0.0.0，确保 Docker 能通过 host.docker.internal 访问到
        start_http_server(8089, addr="0.0.0.0")
        logging.info("Prometheus 探针已启动，监听端口: 8089")
    except Exception as e:
        logging.error(f"探针启动失败 (端口可能被占用): {e}")

@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, context, **kwargs):
    """每次请求结束时触发，记录 TPS 和响应时间"""
    result = "fail" if exception else "success"
    locust_requests_total.labels(method=request_type, name=name, result=result).inc()
    if response_time is not None:
        locust_request_latency_seconds.labels(method=request_type, name=name).observe(response_time / 1000.0)

@events.user_count.add_listener
def on_user_count(user_count, **kwargs):
    """记录实时并发用户数"""
    locust_users.set(user_count)


# ==========================================
# 2. 原有的 HttpRunner 压测业务逻辑
# ==========================================
class HttpRunnerUser(HttpUser):
    host = ""
    wait_time = between(5, 15)

    def on_start(self):
        locust_tests = prepare_locust_tests()
        self.testcase_runners = [
            testcase().with_session(self.client) for testcase in locust_tests
        ]

    @task
    def test_any(self):
        test_runner = random.choice(self.testcase_runners)
        try:
            test_runner.run()
        except Exception as ex:
            self.environment.events.request_failure.fire(
                request_type="Failed",
                name=test_runner.config.name,
                response_time=0,
                response_length=0,
                exception=ex,
            )
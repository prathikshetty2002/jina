import os

import pytest

import jina.clients.base.grpc
from jina import Client, Flow


@pytest.fixture
def error_log_level():
    old_env = os.environ.get('JINA_LOG_LEVEL')
    os.environ['JINA_LOG_LEVEL'] = 'ERROR'
    yield
    os.environ['JINA_LOG_LEVEL'] = old_env


def test_grpc_with_metadata(error_log_level):
    import grpc

    from jina.serve.runtimes.gateway.grpc import (
        GRPCGatewayRuntime as _GRPCGatewayRuntime,
    )

    class GRPCGatewayRuntime(_GRPCGatewayRuntime):
        async def async_setup(self):
            """
            The async method to setup.

            Create the gRPC server and expose the port for communication.
            """

            class AuthInterceptor(grpc.aio.ServerInterceptor):
                def __init__(self, key):
                    self._valid_metadata = ('rpc-auth-header', key)

                    def deny(_, context):
                        context.abort(grpc.StatusCode.UNAUTHENTICATED, 'Invalid key')

                    self._deny = grpc.unary_unary_rpc_method_handler(deny)

                async def intercept_service(self, continuation, handler_call_details):
                    meta = handler_call_details.invocation_metadata
                    for m in meta:
                        if m == self._valid_metadata:
                            return await continuation(handler_call_details)

                    return self._deny

            if not self.args.proxy and os.name != 'nt':
                os.unsetenv('http_proxy')
                os.unsetenv('https_proxy')

            self.server = grpc.aio.server(
                interceptors=(AuthInterceptor('access_key'),),
                options=[
                    ('grpc.max_send_message_length', -1),
                    ('grpc.max_receive_message_length', -1),
                ],
            )

            self._set_topology_graph()
            self._set_connection_pool()

            await self._async_setup_server()

    import jina
    from jina.serve.runtimes.gateway import grpc as _grpc

    _grpc.GRPCGatewayRuntime = GRPCGatewayRuntime

    with Flow(
        protocol='grpc',
    ) as f:
        c = Client(port=f.port)

        meta_data = (('rpc-auth-header', 'access_key'),)
        c.post(on='/', metadata=meta_data)

        with pytest.raises(jina.clients.base.grpc.BadClient):
            meta_data = (('rpc-auth-header', 'invalid_access_key'),)
            c.post(on='/', metadata=meta_data)

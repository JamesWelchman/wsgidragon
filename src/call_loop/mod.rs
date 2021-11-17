use std::collections::HashMap;
use std::sync::mpsc::{Receiver, Sender, TryRecvError};

pub struct CallSend {
    pub id: i32,
    pub timeout_ms: u64,

    // HTTP stuff
    pub method: String,
    pub host: String,
    pub port: u16,
    pub path_segms: Vec<String>,
    pub use_ssl: bool,
    pub params: Vec<(String, String)>,
    pub headers: Vec<(String, String)>,
    pub body: Vec<u8>,
}

pub struct CallRecv {
    pub id: i32,
    pub call_result: CallResult,
}

pub struct CallResponse {
    pub code: u16,
    pub headers: Vec<(String, String)>,
    pub body: Vec<u8>,
}

#[derive(Debug)]
pub struct CallError {
    pub action: &'static str,
    pub err: mio_httpc::Error,
}

#[derive(Copy, Clone, Debug)]
enum State {
    Send,
    Recv,
}

struct PendingRequest {
    id: i32,
    call: mio_httpc::Call,
    state: State,
    code: u16,
    headers: Vec<(String, String)>,
    body: Vec<u8>,
}

impl From<PendingRequest> for CallRecv {
    fn from(p: PendingRequest) -> Self {
        Self {
            id: p.id,
            call_result: CallResult::Ok(CallResponse {
                code: p.code,
                headers: p.headers,
                body: p.body,
            }),
        }
    }
}

impl PendingRequest {
    fn new(id: i32, call: mio_httpc::Call) -> Self {
        Self {
            id,
            call,
            state: State::Send,
            code: 0,
            headers: vec![],
            body: Vec::with_capacity(4096),
        }
    }
}

pub type CallResult = std::result::Result<CallResponse, CallError>;

fn get_call_send(inq: &Receiver<CallSend>, block: bool) -> Option<Option<CallSend>> {
    if block {
        // If we error here, return None - thus signalling to close the loop
        inq.recv().map(|r| Some(r)).ok()
    } else {
        inq.try_recv()
            .map(|r| Some(r))
            .or_else(|e| match e {
                TryRecvError::Disconnected => Err(TryRecvError::Disconnected),
                TryRecvError::Empty => Ok(None),
            })
            .ok()
    }
}

fn create_call(
    call_send: CallSend,
    httpc: &mut mio_httpc::Httpc,
    poll: &mut mio::Poll,
) -> Result<mio_httpc::Call, CallError> {
    let mut builder = mio_httpc::CallBuilder::new();
    builder
        .method(&call_send.method)
        .host(&call_send.host)
        .port(call_send.port)
        .path_segms(
            &(call_send
                .path_segms
                .iter()
                .map(|s| &s[..])
                .collect::<Vec<&str>>()),
        )
        .set_https(call_send.use_ssl)
        .timeout_ms(call_send.timeout_ms)
        .max_redirects(0)
        .gzip(true);

    for (key, value) in call_send.params.iter() {
        builder.query(key, value);
    }

    for (key, value) in call_send.headers.iter() {
        builder.header(key, value);
    }

    // Tell the server we don't have a cache
    builder.header("Cache-Control", "no-cache");

    if !call_send.body.is_empty() {
        builder.body(call_send.body);
    }

    // Place the call
    let call = builder
        .call(httpc, poll.registry())
        .map_err(|e| CallError {
            action: "couldn't create call",
            err: e,
        })?;

    Ok(call)
}

pub fn run_forever(inq: &Receiver<CallSend>, outq: &Sender<CallRecv>) -> mio_httpc::Result<()> {
    let mut poll = mio::Poll::new()?;
    let mut httpc = mio_httpc::Httpc::new(10, None);
    let mut events = mio::Events::with_capacity(128);
    let mut pending_calls = HashMap::new();
    let mut cref_to_id = HashMap::new();

    loop {
        let call_send = match get_call_send(inq, pending_calls.is_empty()) {
            None => break Ok(()),
            Some(call_send) => call_send,
        };

        if let Some(call_send) = call_send {
            let id = call_send.id;

            match create_call(call_send, &mut httpc, &mut poll) {
                Ok(call) => {
                    cref_to_id.insert(call.get_ref(), id);
                    pending_calls.insert(id, PendingRequest::new(id, call));
                }
                Err(e) => {
                    // Send the error to the caller
                    let r = outq.send(CallRecv {
                        id,
                        call_result: CallResult::Err(e),
                    });

                    // If the receiver has been dropped
                    // then exit the loop.
                    if r.is_err() {
                        break Ok(());
                    }
                }
            }
        }

        // Take any events we have
        poll.poll(&mut events, None)?;

        for ev in events.iter() {
            let cref = match httpc.event(&ev) {
                Some(c) => c,
                None => continue,
            };
            let id = match cref_to_id.get(&cref) {
                Some(i) => *i,
                None => {
                    cref_to_id.remove(&cref);
                    continue;
                }
            };
            let mut send_resp = false;
            let mut err: Option<CallError> = None;
            let mut new_cref: Option<mio_httpc::CallRef> = None;

            if let Some(mut pending_req) = pending_calls.get_mut(&id) {
                let call = &mut pending_req.call;
                let buf = &mut pending_req.body;

                if let State::Send = pending_req.state {
                    use mio_httpc::SendState;
                    match httpc.call_send(poll.registry(), call, None) {
                        SendState::Error(e) => {
                            err = Some(CallError {
                                action: "couldn't send request",
                                err: e,
                            });
                            send_resp = true;
                        }
                        SendState::Receiving => {
                            pending_req.state = State::Recv;
                        }
                        _ => {}
                    }
                }

                if let State::Recv = pending_req.state {
                    use mio_httpc::RecvState;
                    match httpc.call_recv(poll.registry(), call, Some(buf)) {
                        RecvState::Error(e) => {
                            send_resp = true;
                            err = Some(CallError {
                                err: e,
                                action: "couldn't receive response",
                            });
                        }
                        RecvState::Response(resp, sz) => {
                            // Handle resp
                            pending_req.code = resp.status;
                            pending_req.headers = build_headers(resp.headers());

                            if sz.is_empty() {
                                // We're done
                                send_resp = true;
                            }
                        }
                        RecvState::ReceivedBody(_) => {
                            // Body complete
                            send_resp = true;
                        }
                        RecvState::Sending => {
                            buf.clear();
                            pending_req.state = State::Send;
                            new_cref = Some(call.get_ref());
                        }
                        _ => {}
                    }
                }
            }

            // Do we replace the cref?
            if let Some(new_cref) = new_cref {
                cref_to_id.insert(new_cref, id);
            }

            // Do we send a response?
            if send_resp {
                let pending_req = pending_calls.remove(&id).expect("expected pending req");

                let r = outq.send(match err {
                    None => pending_req.into(),
                    Some(e) => CallRecv {
                        id: pending_req.id,
                        call_result: CallResult::Err(e),
                    },
                });

                if r.is_err() {
                    // Couldn't send - close loop
                    return Ok(());
                }
            }
        }
    }
}

fn build_headers(hs: mio_httpc::Headers) -> Vec<(String, String)> {
    hs.map(|h| (h.name.to_owned(), h.value.to_owned()))
        .collect::<Vec<(String, String)>>()
}

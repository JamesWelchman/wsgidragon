use std::collections::{HashMap, HashSet};
use std::ops::Add;
use std::panic;
use std::sync::mpsc::{channel, Receiver, Sender};
use std::sync::Arc;
use std::thread::sleep;
use std::thread::Builder as ThreadBuilder;
use std::time;

use pyo3::exceptions::{PyOSError, PyRuntimeError, PyTimeoutError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};

mod call_loop;

#[pyclass]
struct CallResponse {
    inner: Arc<call_loop::CallRecv>,
}

#[pymethods]
impl CallResponse {
    fn log_tags(&self, py: Python) -> PyResult<Py<PyDict>> {
        let dct = PyDict::new(py);

        match self.inner.call_result {
            Ok(ref r) => {
                dct.set_item("http.code", r.code)?;
                dct.set_item("http.resp_content_length", r.body.len())?;
            }
            Err(ref e) => {
                dct.set_item("error", format!("{:?}", e))?;
            }
        }

        Ok(dct.into())
    }

    // get returns either a HttpResponse _or_ an exception
    fn get(&self, py: Python) -> PyResult<PyObject> {
        match self.inner.call_result {
            Ok(ref resp) => {
                let resp = HttpResponse {
                    code: resp.code,
                    headers: resp.headers.to_owned(),
                    body: resp.body.to_owned(),
                };

                PyCell::new(py, resp).map(|v| v.to_object(py))
            }
            Err(ref e) => Ok(build_exc(e).to_object(py)),
        }
    }
}

fn build_exc(e: &call_loop::CallError) -> PyErr {
    use mio_httpc::Error;
    let msg = format!("{} - {:?}", e.action, e.err);
    match e.err {
        Error::Io(_) => PyOSError::new_err(msg),
        Error::TimeOut => PyTimeoutError::new_err(msg),
        _ => PyRuntimeError::new_err(msg),
    }
}

#[pyclass]
struct HttpResponse {
    code: u16,
    headers: Vec<(String, String)>,
    body: Vec<u8>,
}

#[pymethods]
impl HttpResponse {
    #[getter]
    fn get_code(&self) -> u16 {
        self.code
    }

    #[getter]
    fn get_content_length(&self) -> usize {
        self.body.len()
    }

    fn headers(&self, py: Python) -> Py<PyList> {
        PyList::new(
            py,
            self.headers.iter().map(|(h, v)| PyTuple::new(py, [h, v])),
        )
        .into()
    }

    #[getter]
    fn get_body(&self) -> &[u8] {
        &self.body
    }
}

#[pyclass]
struct InnerCaller {
    inq: Sender<call_loop::CallSend>,
    outq: Receiver<call_loop::CallRecv>,

    pending_reqs: HashSet<i32>,
    completed_reqs: HashMap<i32, Arc<call_loop::CallRecv>>,
    id: i32,

    // trace params
    trace: Option<(String, String)>,
    client: Option<String>,
}

#[derive(serde::Serialize)]
struct LogErrorMessage<'s> {
    service: &'s str,
    msg: &'static str,
    error: String,
    level: &'static str,
}

#[pymethods]
impl InnerCaller {
    #[new]
    fn new(service_name: String) -> Self {
        let (inq_s, inq_r) = channel();
        let (outq_s, outq_r) = channel();

        ThreadBuilder::new()
            .name("call_loop".to_string())
            .spawn(move || loop {
                if let Err(e) = call_loop::run_forever(&inq_r, &outq_s) {
                    // Log the error to stdout in JSON
                    let msg = LogErrorMessage {
                        service: &service_name,
                        msg: "call_loop exited",
                        level: "ERROR",
                        error: format!("{:?}", e),
                    };

                    match serde_json::to_string(&msg) {
                        Ok(s) => println!("{}", s),
                        Err(e) => eprintln!("couldn't log error - {:?}", e),
                    }

                    // restart the loop
                    sleep(time::Duration::from_secs(1));
                    continue;
                }

                break;
            })
            .expect("couldn't spawn call_loop thread");

        Self {
            pending_reqs: HashSet::new(),
            completed_reqs: HashMap::new(),
            id: 0,
            inq: inq_s,
            outq: outq_r,
            trace: None,
            client: None,
        }
    }

    fn call(
        &mut self,
        method: String,
        host: String,
        port: u16,
        path_segms: Vec<String>,
        use_ssl: bool,
        params: Vec<(String, String)>,

        mut headers: Vec<(String, String)>,
        body: Vec<u8>,
        timeout_ms: u64,
    ) -> PyResult<i32> {
        if let Some((ref trace_id, ref parent_id)) = self.trace {
            headers.push((
                "Traceparent".to_string(),
                format!("00-{}-{}-00", trace_id, parent_id),
            ));
        }

        if let Some(ref client) = self.client {
            headers.push(("X-Client".to_string(), client.to_owned()));
        }

        // X-Timeout header
        let x_timeout = time::SystemTime::now()
            .add(time::Duration::from_millis(timeout_ms))
            .duration_since(time::UNIX_EPOCH)
            .expect("couldn't compute system time")
            .as_secs();

        headers.push(("X-Timeout".to_string(), format!("{}", x_timeout)));

        let id = self.get_id();
        self.pending_reqs.insert(id);

        self.inq
            .send(call_loop::CallSend {
                id,
                timeout_ms,
                method,
                host,
                port,
                path_segms,
                use_ssl,
                params,
                headers,
                body,
            })
            .map_err(|e| PyRuntimeError::new_err(format!("couldn't send request - {:?}", e)))?;
        Ok(id)
    }

    fn clear(&mut self) {
        self.pending_reqs.clear();
        self.completed_reqs.clear();
    }

    fn set_trace(&mut self, trace_id: &str, parent_id: &str) {
        self.trace = Some((trace_id.to_string(), parent_id.to_string()))
    }

    fn set_client(&mut self, client: &str) {
        self.client = Some(client.to_string())
    }

    fn poll_ready(&mut self, id: i32) -> PyResult<Option<CallResponse>> {
        self.tick()?;

        Ok(self.completed_reqs.get(&id).map(|call_recv| CallResponse {
            inner: call_recv.clone(),
        }))
    }

    fn block_on_ids(&mut self, ids: Vec<i32>) -> PyResult<i32> {
        for id in ids.iter() {
            if self.pending_reqs.get(id).is_none() {
                // Invalid ID
                panic!("id is invalid");
            }
        }

        for &i in ids.iter() {
            if let Some(_) = self.poll_ready(i)? {
                return Ok(i);
            }
        }

        // Block, waiting for an id to become ready
        loop {
            match self.outq.recv() {
                Ok(r) => {
                    let id = r.id;
                    self.add_call_recv(r)?;
                    if ids.contains(&id) {
                        break Ok(id);
                    }
                }
                Err(e) => {
                    println!("couldn't recv on outq {:?}", e);
                    panic!("recv q crashed");
                }
            }
        }
    }
}

impl InnerCaller {
    fn tick(&mut self) -> PyResult<()> {
        // Do we have anything on the outq?
        loop {
            match self.outq.try_recv() {
                Ok(r) => self.add_call_recv(r)?,
                Err(_) => break,
            }
        }
        Ok(())
    }

    fn add_call_recv(&mut self, r: call_loop::CallRecv) -> PyResult<()> {
        if let Some(&id) = self.pending_reqs.get(&r.id) {
            self.completed_reqs.insert(id, Arc::new(r));
        }

        Ok(())
    }

    fn get_id(&mut self) -> i32 {
        self.id += 1;
        return self.id;
    }
}

#[pymodule]
fn wsgidragoncall(_: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<InnerCaller>()
}

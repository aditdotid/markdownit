import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set
from config import BATCH_DEBOUNCE_SECONDS

logger = logging.getLogger(__name__)


@dataclass
class QueuedFile:
    file_id: str
    file_name: str
    file_size: int
    telegram_file_obj: Any


@dataclass
class BatchJob:
    job_id: str
    chat_id: int
    files: List[QueuedFile]
    status_message_id: Optional[int] = None


@dataclass
class PendingBatch:
    chat_id: int
    files: List[QueuedFile] = field(default_factory=list)
    timer_task: Optional[asyncio.Task] = None
    status_message_id: Optional[int] = None


class BatchManager:
    """
    Mengelola pengelompokan file beruntun (debouncing) dan antrean pemrosesan
    asinkron per chat (FIFO Queue Worker) agar tidak terjadi crash saat user
    mengirim file baru ketika proses konversi sebelumnya masih berjalan.
    """

    def __init__(
        self,
        process_callback: Callable[[int, List[QueuedFile], Optional[int]], Coroutine],
        notify_queued_callback: Optional[Callable[[int, int, int], Coroutine]] = None,
    ):
        self._callback = process_callback
        self._notify_queued_callback = notify_queued_callback

        # Debounce tracking per chat_id
        self._pending_batches: Dict[int, PendingBatch] = {}

        # FIFO Queue & Worker tracking per chat_id
        self._job_queues: Dict[int, asyncio.Queue] = {}
        self._active_workers: Set[int] = set()

        self._lock = asyncio.Lock()

    async def add_file(
        self,
        chat_id: int,
        queued_file: QueuedFile,
        status_message_id: Optional[int] = None,
    ) -> int:
        """
        Menambahkan file ke antrean debouncing untuk chat_id tertentu.
        Jika ada file berikutnya dalam jeda debounce, timer di-reset.
        """
        async with self._lock:
            if chat_id not in self._pending_batches:
                self._pending_batches[chat_id] = PendingBatch(
                    chat_id=chat_id,
                    status_message_id=status_message_id,
                )

            batch = self._pending_batches[chat_id]
            batch.files.append(queued_file)
            if status_message_id and not batch.status_message_id:
                batch.status_message_id = status_message_id

            # Batalkan debounce timer sebelumnya
            if batch.timer_task and not batch.timer_task.done():
                batch.timer_task.cancel()

            # Jadwalkan debounce timer baru
            batch.timer_task = asyncio.create_task(
                self._debounce_wait(chat_id, BATCH_DEBOUNCE_SECONDS)
            )

            return len(batch.files)

    async def _debounce_wait(self, chat_id: int, delay: float):
        """Menunggu jeda debounce selesai, lalu memasukkan batch ke antrean eksekusi."""
        try:
            await asyncio.sleep(delay)

            async with self._lock:
                pending = self._pending_batches.pop(chat_id, None)

            if not pending or not pending.files:
                return

            job = BatchJob(
                job_id=uuid.uuid4().hex[:8],
                chat_id=chat_id,
                files=pending.files,
                status_message_id=pending.status_message_id,
            )

            await self._enqueue_job(job)

        except asyncio.CancelledError:
            # Dibatalkan karena ada file baru masuk dalam jendela debounce
            pass
        except Exception as e:
            logger.error(f"Error dalam debounce wait untuk chat {chat_id}: {e}", exc_info=True)

    async def _enqueue_job(self, job: BatchJob):
        """Memasukkan tugas batch ke antrean per-chat dan memastikan worker aktif."""
        async with self._lock:
            chat_id = job.chat_id
            if chat_id not in self._job_queues:
                self._job_queues[chat_id] = asyncio.Queue()

            queue = self._job_queues[chat_id]
            is_worker_running = chat_id in self._active_workers
            queue_position = queue.qsize() + 1  # Urutan dalam antrean

            await queue.put(job)
            logger.info(
                f"Job {job.job_id} dimasukkan ke queue chat_id={chat_id}. "
                f"Posisi: {queue_position}, File: {len(job.files)}, Worker aktif: {is_worker_running}"
            )

            if not is_worker_running:
                self._active_workers.add(chat_id)
                asyncio.create_task(self._run_chat_worker(chat_id))
            else:
                # Beritahu pengguna bahwa file mereka telah masuk ke antrean
                if self._notify_queued_callback:
                    asyncio.create_task(
                        self._notify_queued_callback(
                            chat_id, queue_position, len(job.files)
                        )
                    )

    async def _run_chat_worker(self, chat_id: int):
        """
        Worker asinkron untuk satu chat.
        Memproses satu tugas batch hingga tuntas secara berurutan (FIFO)
        sebelum mengambil tugas berikutnya dari pengguna yang sama.
        """
        logger.info(f"Chat worker dimulai untuk chat_id={chat_id}")
        try:
            while True:
                async with self._lock:
                    queue = self._job_queues.get(chat_id)
                    if not queue or queue.empty():
                        self._active_workers.discard(chat_id)
                        break
                    job: BatchJob = queue.get_nowait()

                try:
                    logger.info(
                        f"Menjalankan job {job.job_id} untuk chat {chat_id} ({len(job.files)} file)"
                    )
                    await self._callback(job.chat_id, job.files, job.status_message_id)
                except Exception as e:
                    logger.error(
                        f"Error saat menjalankan job {job.job_id} untuk chat {chat_id}: {e}",
                        exc_info=True,
                    )
                finally:
                    queue.task_done()

        except Exception as worker_err:
            logger.error(f"Worker chat {chat_id} mengalami error fatal: {worker_err}", exc_info=True)
        finally:
            async with self._lock:
                self._active_workers.discard(chat_id)
            logger.info(f"Chat worker selesai untuk chat_id={chat_id}")

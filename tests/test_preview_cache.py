import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
import sys,time,tempfile,threading,unittest
from pathlib import Path
from pipeline import CONFIG
if CONFIG.get('qt_packages'):sys.path.insert(0,CONFIG['qt_packages'])
from PySide6.QtCore import QCoreApplication,QSize
from PySide6.QtGui import QImage,QColor
from preview_cache import FrameCache

app=QCoreApplication.instance() or QCoreApplication([])


class PreviewCacheTests(unittest.TestCase):
    def make_frames(self,folder,red,count=20):
        folder.mkdir(parents=True,exist_ok=True);poses=[]
        for frame in range(1,count+1):
            name=f'{frame}.png';image=QImage(64,64,QImage.Format_RGB32);image.fill(QColor(red,frame,30));image.save(str(folder/name))
            poses.append(dict(frame=frame,name=name))
        return poses

    def wait_image(self,cache,frame):
        deadline=time.perf_counter()+3
        while time.perf_counter()<deadline:
            app.processEvents();image=cache.get(frame)
            if image is not None:return image
            time.sleep(.005)
        self.fail('Frame prefetch timed out')

    def test_bounded_prefetch_and_exact_seek(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);poses=self.make_frames(folder,80)
            cache=FrameCache(budget=3*20*20*4)
            try:
                cache.configure(folder,poses)
                for frame in (1,8,4,19,2):
                    cache.request(frame,QSize(20,20));image=cache.load_now(frame)
                    self.assertEqual(image.pixelColor(5,5).green(),frame)
                    self.assertEqual(image.size(),QSize(20,20))
                self.wait_image(cache,2)
                with cache.condition:
                    self.assertLessEqual(cache.bytes,cache.budget);self.assertLessEqual(len(cache.todo),cache.ahead+1)
                cache.request(2,QSize(10,10));image=cache.load_now(2)
                self.assertEqual(image.size(),QSize(10,10))
            finally:cache.close()
            self.assertFalse(cache.thread.is_alive())

    def test_old_decode_cannot_replace_new_project(self):
        with tempfile.TemporaryDirectory() as directory:
            a,b=Path(directory)/'a',Path(directory)/'b';poses=self.make_frames(a,20,1);self.make_frames(b,200,1)
            cache=FrameCache();entered=threading.Event();release=threading.Event();decode=cache.decode
            def slow(path,size):
                if str(a) in path:entered.set();release.wait(2)
                return decode(path,size)
            cache.decode=slow
            try:
                cache.configure(a,poses);cache.request(1,QSize(20,20));self.assertTrue(entered.wait(1))
                old_generation=cache.generation;cache.configure(b,poses);cache.request(1,QSize(20,20));release.set()
                image=self.wait_image(cache,1)
                self.assertGreater(cache.generation,old_generation);self.assertEqual(image.pixelColor(5,5).red(),200)
            finally:release.set();cache.close()


if __name__=='__main__':unittest.main()

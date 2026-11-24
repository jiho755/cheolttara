package io.github.jiho755.cheolttara;

import android.Manifest;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ContentValues;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.media.MediaScannerConnection;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.os.Message;
import android.provider.MediaStore;
import android.util.Base64;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.URISyntaxException;

public class MainActivity extends Activity {

    private static final String SITE_URL = "https://jiho755.github.io/cheolttara/";
    private static final String SITE_HOST = "jiho755.github.io";
    private static final String SITE_PATH_PREFIX = "/cheolttara";
    private static final String GALLERY_DIR = "철따라";
    private static final int REQ_FILE_CHOOSER = 1001;
    private static final int REQ_WRITE_STORAGE = 1002;

    private WebView webView;
    private ValueCallback<Uri[]> filePathCallback;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    // API 24-28: 저장 권한을 기다리는 동안 보관하는 이미지
    private byte[] pendingBytes;
    private String pendingName;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        getWindow().setStatusBarColor(Color.parseColor("#fbf8f3"));
        if (Build.VERSION.SDK_INT >= 23) {
            View decor = getWindow().getDecorView();
            decor.setSystemUiVisibility(decor.getSystemUiVisibility() | View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR);
        }

        webView = new WebView(this);
        webView.setLayoutParams(new ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        webView.setBackgroundColor(Color.parseColor("#fbf8f3"));
        setContentView(webView);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        settings.setSupportMultipleWindows(true);
        settings.setJavaScriptCanOpenWindowsAutomatically(true);
        settings.setUserAgentString(settings.getUserAgentString() + " CheolttaraApp");

        webView.addJavascriptInterface(new AndroidBridge(), "CheolttaraAndroid");
        webView.setWebViewClient(new AppWebViewClient());
        webView.setWebChromeClient(new AppWebChromeClient());

        if (savedInstanceState != null) {
            webView.restoreState(savedInstanceState);
        } else {
            webView.loadUrl(SITE_URL);
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        if (webView != null) {
            webView.saveState(outState);
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (webView != null) webView.onResume();
    }

    @Override
    protected void onPause() {
        if (webView != null) webView.onPause();
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            ViewGroup parent = (ViewGroup) webView.getParent();
            if (parent != null) parent.removeView(webView);
            webView.destroy();
            webView = null;
        }
        super.onDestroy();
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            finish();
        }
    }

    // ---------- URL 처리 ----------

    private static boolean isInternal(Uri uri) {
        if (uri == null) return false;
        String scheme = uri.getScheme();
        if (scheme == null) return false;
        scheme = scheme.toLowerCase();
        if (scheme.equals("about") || scheme.equals("blob")) return true;
        if (!scheme.equals("http") && !scheme.equals("https")) return false;
        String host = uri.getHost();
        String path = uri.getPath();
        if (path == null) path = "";
        return host != null && host.equalsIgnoreCase(SITE_HOST) && path.startsWith(SITE_PATH_PREFIX);
    }

    /** 사이트 안이면 WebView 에서, 아니면 외부 앱으로 연다. */
    private void openUrl(String url) {
        if (url == null || url.length() == 0 || url.equals("about:blank")) return;
        Uri uri = Uri.parse(url);
        if (isInternal(uri)) {
            if (webView != null) webView.loadUrl(url);
        } else {
            openExternal(url);
        }
    }

    private void openExternal(String url) {
        try {
            if (url.startsWith("intent:")) {
                Intent intent = Intent.parseUri(url, Intent.URI_INTENT_SCHEME);
                intent.addCategory(Intent.CATEGORY_BROWSABLE);
                intent.setComponent(null);
                intent.setSelector(null);
                try {
                    startActivity(intent);
                } catch (ActivityNotFoundException e) {
                    String fallback = intent.getStringExtra("browser_fallback_url");
                    if (fallback != null && fallback.length() > 0) {
                        startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(fallback)));
                    } else if (intent.getPackage() != null) {
                        startActivity(new Intent(Intent.ACTION_VIEW,
                                Uri.parse("market://details?id=" + intent.getPackage())));
                    }
                }
            } else {
                startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
            }
        } catch (ActivityNotFoundException e) {
            toast("열 수 있는 앱이 없어요");
        } catch (URISyntaxException e) {
            toast("열 수 없는 주소예요");
        } catch (RuntimeException e) {
            toast("열 수 없는 주소예요");
        }
    }

    private void toast(final String msg) {
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                Toast.makeText(MainActivity.this, msg, Toast.LENGTH_SHORT).show();
            }
        });
    }

    private void showOfflinePage() {
        String html = "<!DOCTYPE html><html lang=\"ko\"><head><meta charset=\"utf-8\">"
                + "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
                + "<style>body{margin:0;min-height:100vh;display:flex;flex-direction:column;align-items:center;"
                + "justify-content:center;background:#fbf8f3;color:#3a332d;font-family:sans-serif;text-align:center;padding:24px;box-sizing:border-box}"
                + ".big{font-size:48px}p{font-size:16px;margin:16px 0 24px}"
                + "button{font-size:16px;padding:12px 28px;border:0;border-radius:24px;background:#e07a5f;color:#fff}</style></head><body>"
                + "<div class=\"big\">&#128268;</div>"
                + "<p>인터넷에 연결되면 다시 시도해 주세요</p>"
                + "<button onclick=\"location.replace('" + SITE_URL + "')\">다시 시도</button>"
                + "</body></html>";
        webView.loadDataWithBaseURL(SITE_URL, html, "text/html", "UTF-8", null);
    }

    // ---------- WebViewClient / WebChromeClient ----------

    private class AppWebViewClient extends WebViewClient {
        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            Uri uri = request.getUrl();
            if (isInternal(uri)) return false;
            openExternal(uri.toString());
            return true;
        }

        @Override
        public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
            if (request.isForMainFrame()) {
                showOfflinePage();
            }
        }
    }

    private class AppWebChromeClient extends WebChromeClient {
        @Override
        public boolean onCreateWindow(WebView view, boolean isDialog, boolean isUserGesture, Message resultMsg) {
            final WebView temp = new WebView(MainActivity.this);
            temp.setWebViewClient(new WebViewClient() {
                private boolean handled = false;

                private void handle(String url) {
                    if (handled || url == null || url.length() == 0 || url.equals("about:blank")) return;
                    handled = true;
                    openUrl(url);
                    mainHandler.post(new Runnable() {
                        @Override
                        public void run() {
                            temp.destroy();
                        }
                    });
                }

                @Override
                public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest request) {
                    handle(request.getUrl().toString());
                    return true;
                }

                @Override
                public void onPageStarted(WebView v, String url, android.graphics.Bitmap favicon) {
                    handle(url);
                }
            });
            WebView.WebViewTransport transport = (WebView.WebViewTransport) resultMsg.obj;
            transport.setWebView(temp);
            resultMsg.sendToTarget();
            return true;
        }

        @Override
        public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback,
                                         FileChooserParams fileChooserParams) {
            if (filePathCallback != null) {
                filePathCallback.onReceiveValue(null);
            }
            filePathCallback = callback;
            try {
                Intent intent = fileChooserParams.createIntent();
                startActivityForResult(intent, REQ_FILE_CHOOSER);
            } catch (ActivityNotFoundException e) {
                try {
                    Intent fallback = new Intent(Intent.ACTION_GET_CONTENT);
                    fallback.addCategory(Intent.CATEGORY_OPENABLE);
                    fallback.setType("image/*");
                    startActivityForResult(Intent.createChooser(fallback, "사진 선택"), REQ_FILE_CHOOSER);
                } catch (ActivityNotFoundException e2) {
                    filePathCallback = null;
                    callback.onReceiveValue(null);
                    return false;
                }
            }
            return true;
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == REQ_FILE_CHOOSER) {
            if (filePathCallback != null) {
                Uri[] result = null;
                if (resultCode == RESULT_OK) {
                    result = WebChromeClient.FileChooserParams.parseResult(resultCode, data);
                }
                filePathCallback.onReceiveValue(result);
                filePathCallback = null;
            }
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    // ---------- 갤러리 저장 ----------

    public class AndroidBridge {
        @JavascriptInterface
        public boolean saveImage(String base64Png, String fileName) {
            byte[] bytes;
            try {
                bytes = Base64.decode(base64Png, Base64.DEFAULT);
            } catch (RuntimeException e) {
                toast("저장하지 못했어요");
                return false;
            }
            if (bytes == null || bytes.length == 0) {
                toast("저장하지 못했어요");
                return false;
            }
            String name = sanitizeName(fileName);

            if (Build.VERSION.SDK_INT < 29
                    && checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) {
                // 권한 허용 후 onRequestPermissionsResult 에서 저장한다. (이 호출은 false 를 돌려줌)
                pendingBytes = bytes;
                pendingName = name;
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        requestPermissions(new String[]{Manifest.permission.WRITE_EXTERNAL_STORAGE}, REQ_WRITE_STORAGE);
                    }
                });
                return false;
            }
            boolean ok = writeToGallery(bytes, name);
            toast(ok ? "갤러리에 저장했어요" : "저장하지 못했어요");
            return ok;
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode != REQ_WRITE_STORAGE) return;
        final byte[] bytes = pendingBytes;
        final String name = pendingName;
        pendingBytes = null;
        pendingName = null;
        if (bytes != null && name != null && grantResults.length > 0
                && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
            new Thread(new Runnable() {
                @Override
                public void run() {
                    boolean ok = writeToGallery(bytes, name);
                    toast(ok ? "갤러리에 저장했어요" : "저장하지 못했어요");
                }
            }).start();
        } else {
            toast("저장 권한이 필요해요");
        }
    }

    private static String sanitizeName(String fileName) {
        String name = fileName == null ? "" : fileName.replaceAll("[\\\\/:*?\"<>|]", "_").trim();
        if (name.length() == 0) name = "철따라.png";
        if (!name.toLowerCase().endsWith(".png")) name = name + ".png";
        return name;
    }

    private boolean writeToGallery(byte[] bytes, String name) {
        try {
            if (Build.VERSION.SDK_INT >= 29) {
                ContentValues values = new ContentValues();
                values.put(MediaStore.MediaColumns.DISPLAY_NAME, name);
                values.put(MediaStore.MediaColumns.MIME_TYPE, "image/png");
                values.put(MediaStore.MediaColumns.RELATIVE_PATH, "Pictures/" + GALLERY_DIR);
                values.put(MediaStore.MediaColumns.IS_PENDING, 1);
                Uri uri = getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values);
                if (uri == null) return false;
                try {
                    OutputStream out = getContentResolver().openOutputStream(uri);
                    if (out == null) {
                        getContentResolver().delete(uri, null, null);
                        return false;
                    }
                    try {
                        out.write(bytes);
                    } finally {
                        out.close();
                    }
                    ContentValues done = new ContentValues();
                    done.put(MediaStore.MediaColumns.IS_PENDING, 0);
                    getContentResolver().update(uri, done, null, null);
                    return true;
                } catch (IOException e) {
                    getContentResolver().delete(uri, null, null);
                    return false;
                }
            } else {
                File dir = new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_PICTURES), GALLERY_DIR);
                if (!dir.exists() && !dir.mkdirs()) return false;
                File file = new File(dir, name);
                FileOutputStream out = new FileOutputStream(file);
                try {
                    out.write(bytes);
                } finally {
                    out.close();
                }
                MediaScannerConnection.scanFile(this, new String[]{file.getAbsolutePath()}, new String[]{"image/png"}, null);
                return true;
            }
        } catch (IOException e) {
            return false;
        } catch (RuntimeException e) {
            return false;
        }
    }
}

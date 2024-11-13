let mediaMixin = {
  data: {
    mediaDialog: false,
    shapefileDialog: false,

    medias: [],
    mediaCats: translations.mediaCats,

    //media edit / create item
    editedMediaIndex: -1,
    editedMedia: {
      title: "",
    },
    editedShapefile: {
      title: "",
    },
    isShapefileCurrentlyUploading: false,
    shapefileExtensions: ["shp", "shx", "dbf", "prj", "cpg", "sbn", "sbx"],

    defaultMedia: {
      title: "",
      files: [],
      category: "",
    },

    mediaTitle__: true,

    //disable btn initially, enable after upload is successful
    upMediaBtnDisabled: true,
    videoDialog: false,
    playerOptions: {},
    videoMeta: {},
    screenshots: [],
    //hold different cropper attributes
    cropper: {
      canvas: null,
      tool: null,
      active: false,
    },
  },

  computed: {
    enableAttach() {
      return this.editedMedia.files && this.editedMedia.files.length > 0;
    },
    enableShapefileUpload() {
      if (!this.editedShapefile.files?.length) return false;
      const requiredFiles = ["shp", "shx", "dbf", "prj"];
      const currentFileTypes = this.editedShapefile.files.map((file) => file.name.split(".").pop());
      // check title isn't just spaces
      const isSpaces = this.editedShapefile.title?.match(/^\s*$/);
      return requiredFiles.every((file) => currentFileTypes.includes(file)) && this.editedShapefile.title?.length > 0 && !isSpaces;
    },
    extensionToIsAdded() {
      return r = this.shapefileExtensions.reduce((acc, ext) => {
        acc[ext] = this.fileExtensionHasBeenAdded(ext);
        return acc;
      }, {});
    },
  },

  methods: {
    fileExtensionHasBeenAdded(extension) {
      if (!this.editedShapefile.files) return false;
      return this.editedShapefile.files.some((file) => file.name.split(".").pop() === extension);
    },

    showError(err, message) {
      this.showSnack(message);
    },

    fileSending(file, xhr, formData) {
      formData.set("etagClient", file.etagClient);
    },

    fileAdded(file) {
      const dropzone = this.$refs.dropzone.dropzone;
      if (dropzone.files.length) {
        var _i, _len;
        for (
          _i = 0, _len = dropzone.files.length;
          _i < _len - 1;
          _i++ // -1 to exclude current file
        ) {
          if (
            dropzone.files[_i].name === file.name &&
            dropzone.files[_i].size === file.size &&
            dropzone.files[_i].lastModified.toString() ===
              file.lastModified.toString()
          ) {
            dropzone.removeFile(file);
          }
        }
      }
    },

    shapefileAdded(file) {
      const dropzone = this.$refs.shapefileDropzone.dropzone;
      const isInvalidExtension = !this.shapefileExtensions.includes(file.name.split(".").pop());
      if (isInvalidExtension) {
        dropzone.removeFile(file);
        return;
      }
      for (let i = 0; i < dropzone.files.length - 1; i++) {
        const fileType = dropzone.files[i].name.split(".").pop();
        const addedFileType = file.name.split(".").pop();
        if (fileType === addedFileType) {
          dropzone.removeFile(file);
          this.showError("_", "File type already exists");
          return;
        }
      }
      this.editedShapefile.files.push(file);
    },

    fileRemoved(file, error, xhr) {
      if (!error) {
        // pop out that specific removed file based on UUID
        this.editedMedia.files = this.editedMedia.files.filter(
          (x) => x.uuid !== file.upload.uuid,
        );
      }
    },

    shapefileRemoved(file, error, xhr) {
      if (!error) {
        this.editedShapefile.files = this.editedShapefile.files.filter(
          (x) => x.upload.uuid !== file.upload.uuid,
        );
      }
    },

    uploadSuccess(dzfile) {
      // pick file from dropzone files list
      const needle = this.$refs.dropzone
        .getAcceptedFiles()
        .filter((x) => x.status === "success")
        .filter((x) => parseResponse(x).uuid === dzfile.upload.uuid)
        .pop();

      const file = parseResponse(needle);

      // parse the response in xhr
      this.editedMedia.files.push(file);
      this.upMediaBtnDisabled = false;
    },

    shapefileUploadSuccess(file) {
      // Check if response content type is json
      const response = JSON.parse(file.xhr.response);
      if (!response.completed) return;
      this.isShapefileCurrentlyUploading = false;
      const mediaItem = {};
      mediaItem.title = response.title
      mediaItem.fileType = 'geojson'
      mediaItem.filename = response.filename
      mediaItem.shapefile_group_uuid = response.shapefile_group_uuid
      this.editedItem.medias.push(mediaItem);
    },

    viewImage(item) {
      viewer.show(item);
    },

    crop() {
      if (this.cropper.active) {
        document.querySelector(".croppr-container").remove();
        this.cropper.active = false;
        return;
      }
      let video = this.$el.querySelector("#player video");
      video.pause();

      this.cropper.canvas = document.createElement("canvas");
      this.cropper.canvas.width = this.videoMeta.width;
      this.cropper.canvas.height = this.videoMeta.height;
      let context = this.cropper.canvas.getContext("2d");
      context.fillRect(
        0,
        0,
        this.cropper.canvas.width,
        this.cropper.canvas.height,
      );
      context.drawImage(
        video,
        0,
        0,
        this.cropper.canvas.width,
        this.cropper.canvas.height,
      );
      let img = document.querySelector("#cropImg");
      if (!img) {
        img = new Image();
        img.id = "cropImg";

        this.$el.querySelector(".crop").prepend(img);
      }
      img.src = this.cropper.canvas.toDataURL("image/jpeg");
      (this.cropper.time = Math.round(video.currentTime * 10) / 10),
        (this.cropper.tool = new Croppr(img));
      this.cropper.active = true;
    },

    attachCrop() {
      let crop = this.cropper.tool.getValue();
      let img = this.$el.querySelector(".croppr-image");

      let id = this.screenshots.length;
      let video = this.$el.querySelector("#player video");

      let media = {
        width: crop.width,
        height: crop.height,
        time: this.cropper.time,
        fileType: "image/jpeg",
        filename: video.src.getFilename(),
        ready: false,
        overlay: false,
        sw: true,
      };

      this.screenshots.push(media);
      // wait until data binding is in effect
      this.$nextTick(() => {
        let canvas = this.$el.querySelector(".canvas" + id);
        canvas.width = media.width;
        canvas.height = media.height;
        // calculate ration based on widht/height

        let context = canvas.getContext("2d");
        context.fillRect(0, 0, media.width, media.height);
        context.drawImage(
          img,
          crop.x,
          crop.y,
          media.width,
          media.height,
          0,
          0,
          media.width,
          media.height,
        );

        //clear source image

        this.$el.querySelector(".croppr-container").remove();
        this.cropper.active = false;
      });
    },

    snapshot() {
      let id = this.screenshots.length;
      let video = this.$el.querySelector("#player video");
      video.pause();

      let media = {
        width: this.videoMeta.width,
        height: this.videoMeta.height,
        time: Math.round(video.currentTime * 10) / 10,
        fileType: "image/jpeg",
        filename: video.src.getFilename(),
        ready: false,
        overlay: false,
        sw: true,
      };

      this.screenshots.push(media);
      // wait until data binding is in effect
      this.$nextTick(() => {
        let canvas = this.$el.querySelector(".canvas" + id);

        canvas.width = media.width;
        canvas.height = media.height;
        let context = canvas.getContext("2d");
        context.fillRect(0, 0, media.width, media.height);
        context.drawImage(video, 0, 0, media.width, media.height);
      });
    },
    removeSnapshot(e, index) {
      //this.screenshots.splice(index,1);
      this.screenshots[index].deleted = true;
      // force Vue to re-render the UI
      this.$forceUpdate();
    },
    uploadSnapshot(e, index) {
      let media = this.screenshots[index];
      media.overlay = true;
      let canvas = this.$el.querySelector("#screenshots .canvas" + index);
      let dataUrl = canvas.toDataURL("image/jpeg");
      let blob = dataUriToBlob(dataUrl);
      let data = new FormData();
      data.append("file", blob, media.filename);

      axios
        .post("/admin/api/media/upload", data, {
          headers: { "content-type": false },
        })
        .then((response) => {
          const serverId = response.data;
          //this.showSnack(response.data);
          media.filename = serverId.filename;
          media.etag = serverId.etag;
          media.overlay = false;
          media.ready = true;

          //this.refresh(this.options);
        })
        .catch((err) => {
          console.error(err.response.data);
          this.showSnack(err.response.data);

          media.error = true;
        })
        .finally(() => {
          media.overlay = false;
        });
    },

    attachSnapshots() {
      // get screenshots excluding deleted ones
      let final = this.screenshots.filter((x) => !x.deleted);

      let skipped = [];

      for (const scr of final) {
        //check uploaded ones
        if (scr.ready) {
          let item = {};
          item.title = scr.title;
          item.title_ar = scr.title_ar;
          item.fileType = scr.fileType;
          item.filename = scr.filename;
          item.etag = scr.etag;
          item.time = scr.time;
          item.category = scr.category;

          // prevent attaching duplicate snapshots
          if (this.editedItem.medias.some((m) => m.etag === item.etag)) {
            skipped.push(item);
          } else {
            this.editedItem.medias.push(item);
          }
        }
      }
      if (skipped?.length) {
        this.showSnack(`${skipped.length} duplicate items skipped.`);
      }

      this.closeVideo();
    },

    viewPlayer(s3url) {
      //open video player
      this.videoDialog = true;
      this.screenshots = [];
      this.$nextTick(() => {
        let pp = document.querySelector("#pp");

        //cleanup pip or existing video
        let ep = pp.querySelector("#player");
        if (ep) {
          videojs(ep).dispose();
        }
        pp.insertAdjacentHTML(
          "afterbegin",
          '<video id="player" controls class="video-js vjs-default-skin vjs-big-play-centered" crossorigin="anonymous" width="620" height="360" preload="auto" ></video>',
        );
        let video = this.$el.querySelector("video");

        videojs(
          video,
          {
            playbackRates: VIDEO_RATES,
          },
          function () {
            this.src(s3url);
          },
        );
        video.addEventListener("loadedmetadata", () => {
          this.videoMeta.filename = video.src.getFilename() + ".jpg";
          this.videoMeta.time = video.currentTime;
          this.videoMeta.width = video.videoWidth;
          this.videoMeta.height = video.videoHeight;
        });
      });
    },

    closeVideo() {
      //dispose player
      let player = this.$el.querySelector("#player video");
      //videojs(player).dispose();
      player.pause();

      this.videoDialog = false;
    },

    addMedia(media, item, index) {
      this.editedMedia = structuredClone(this.defaultMedia);
      //console.log(this.editedEvent);
      //enable below to activate edit mode
      //this.editedMediaIndex = index;

      //reset dual fields display to english
      this.mediaTitle__ = true;

      this.mediaDialog = true;
      //this.locations = this.editedItem.locations;
    },

    generateUUID() {
      return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (
        c,
      ) {
          var r = (Math.random() * 16) | 0,
          v = c == "x" ? r : (r & 0x3) | 0x8;
          return v.toString(16);
        });
      },
    addShapefile(media, item, index) {
      this.editedShapefile = structuredClone(this.defaultMedia);
      this.editedShapefile.uuid = this.generateUUID();

      this.shapefileDialog = true;
    },

    removeMedia: function (fileName) {
      if (confirm("Are you sure?")) {
        const index = this.editedItem.medias.findIndex(
          (x) => x.filename === fileName,
        );
        this.editedItem.medias.splice(index, 1);
      }
    },

    closeMedia() {
      this.editedMedia.files = [];
      this.mediaDialog = false;
      setTimeout(() => {
        this.editedMedia = Object.assign({}, this.defaultMedia);

        this.editedMediaIndex = -1;
      }, 300);
    },

    closeShapefile() {
      this.isShapefileCurrentlyUploading = false;
      this.editedShapefile.files = [];
      this.$refs.shapefileDropzone.removeAllFiles();
      this.shapefileDialog = false;
      setTimeout(() => {
        this.editedShapefile = Object.assign({}, this.defaultMedia);
      }, 300);
    },


    attachMedia() {
      // detect file mode
      if (this.$refs.dropzone) {
        // s3 mode

        for (const file of this.editedMedia.files) {
          let item = {};

          item.title = this.editedMedia.title;
          item.fileType = file.type;
          item.filename = file.filename;
          item.etag = file.etag;
          item.category = this.editedMedia.category;
          item.blur = this.editedMedia.isBlur;
          this.editedItem.medias.push(item);
        }
      } else {
        //console.log(this.editedItem);
        //push files from editedMedia to edited item medias
        for (const file of this.editedMedia.files) {
          let item = {};
          const response = JSON.parse(file.xhr.response);
          item.title = this.editedMedia.title;
          item.fileType = file.type;
          item.filename = response.filename;
          item.uuid = response.upload.uuid;
          item.etag = response.etag;
          this.editedItem.medias.push(item);
        }
      }

      this.$refs.dropzone.removeAllFiles();
      this.closeMedia();
    },

    uploadShapefile() {
      this.$refs.shapefileDropzone.processQueue();
    },

    shapefileQueueComplete() {
      this.closeShapefile();
    },

    shapefileSending(file, xhr, formData) {
      this.isShapefileCurrentlyUploading = true;
      formData.append("title", this.editedShapefile.title);
      formData.append("shapefile_group_uuid", this.editedShapefile.uuid)
      const numFiles = this.editedShapefile.files.length;
      const currentFileNumber = this.editedShapefile.files.indexOf(file) + 1;
      formData.append("numFiles", numFiles);
      formData.append("currentFileNumber", currentFileNumber);
    },

    onFileUploaded(error, file) {
      if (!error) {
        this.upMediaBtnDisabled = false;
      } else {
        if (error.code == 409) {
          this.showSnack("This file already exists in the system");
        } else {
          this.showSnack(
            "Error uploading media. Please check your network connection.",
          );
        }
        console.log(error);
      }
    },
    downloadShapefile(media) {
      var a = document.createElement("a");
      a.href = `/admin/api/media/shapefile/download/${media.shapefile_group_uuid}`;
      a.target = "_blank";
      a.download = `${media.title}-shapefiles.zip`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    }
  },
};
